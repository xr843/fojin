# 对齐层激活运行手册（Prod Activation Runbook）

> 本文是把已合并到 master 的对齐层深化（PR #963/#965/#966）在**生产环境**逐步激活的操作手册。
> 所有脚本都在 **backend 容器内**、且 **DB + embedding API 可达**时运行：`docker compose exec -T backend python scripts/<x>.py ...`。
> 每一步都有：**前置门（Gate）→ 命令 → 验证 → 回滚**。带 ⚠️ 的步骤不可逆或有成本，务必先看 Gate。

配套背景见 [`ALIGNMENT_FLYWHEEL.md`](ALIGNMENT_FLYWHEEL.md)、[`mitra-alignment-integration.md`](mitra-alignment-integration.md)、`backend/docs/mitra-license.md`、`backend/docs/alignment-dataset-card.md`。

---

## 依赖顺序总览

```
Phase 0 去重预检 ──► Phase 1 部署(自动升 0166–0170) ──► Phase 2 回填字符锚点
                                                              │
                          ┌───────────────────────────────────┤
                          ▼                                   ▼
              Phase 3 MITRA(许可→导入→评分→标定)      Phase 5 margin 标定(可独立)
                          │                                   
                          ▼                                   
              Phase 4 句级对齐(refine→验证→翻 flag) ──► 通知建阅读器逐句对读 UI
                          │
                          ▼
              Phase 6 飞轮常态运行(挖候选→人工复核)
```

Phase 3 与 Phase 5 互相独立，可并行；Phase 4 依赖 Phase 2（字符锚点）。

---

## Phase 0 — 部署前预检 ⚠️（Gate for deploy）

### 0a. 核对迁移链起点（务必先做）

CLAUDE.md 反复警告：撞 `down_revision` 会整站宕。部署前先确认 prod 当前版本是 `0166` 的干净祖先（正常应为 `0165`），否则 0166–0170 可能应用不上或撞链：
```bash
docker compose exec -T backend alembic current   # 期望 0165（或已知在 0166 之下的祖先）
docker compose exec -T backend alembic heads      # 期望单头 0170
```
若 prod 不在预期祖先上，**先停下排查**，不要部署。

### 0b. 去重预检

**为什么**：迁移 `0168` 会给 `text_embeddings` 加 `(text_id, juan_num, chunk_index)` 唯一约束，加约束前会在同一事务里**删除重复行**（保留最小 `id`，embeddings 可再生故安全）。先量一下重复规模，避免大表上自联删除意外拖长部署。

**命令**（在 prod 库上，只读）：
```sql
-- 重复规模
SELECT count(*) AS dup_groups, sum(cnt - 1) AS rows_to_delete
FROM (
  SELECT text_id, juan_num, chunk_index, count(*) AS cnt
  FROM text_embeddings GROUP BY 1,2,3 HAVING count(*) > 1
) d;

-- 诊断：重复行的 chunk_text 是否「不同」（真损坏，需排查）还是「相同」（纯重跑副本，可安全删）
SELECT count(*) AS groups_with_divergent_text
FROM (
  SELECT text_id, juan_num, chunk_index
  FROM text_embeddings GROUP BY 1,2,3
  HAVING count(*) > 1 AND count(DISTINCT chunk_text) > 1
) d;
```

**判读**：
- `dup_groups = 0` → 无重复，Phase 1 直接部署。
- 数千级以内、且 `groups_with_divergent_text = 0` → 正常（纯重跑副本），部署时迁移多花几秒~几十秒。
- `groups_with_divergent_text > 0` → 重复行内容不一致，keep-lowest-id 是**任意选择**；先查清为何同位置有不同文本（分块管线问题？），再决定是否直接部署。
- 数十万级 → 先跑一次 `fojin-backup.sh`，并在低峰期部署（自联删除会扫大表）。

---

## Phase 1 — 部署（应用迁移 0166–0170）

**Gate**：Phase 0 已判读；已 `./fojin-backup.sh` 备份（涉及 schema 变更，务必备份）。

**命令**（VPS 上）：
```bash
./deploy.sh
```
`deploy.sh` 检测到 `backend/alembic/` 有改动时会自动执行 `docker compose exec -T backend alembic upgrade head`（幂等，已在 head 则 no-op），随后双副本零停机滚动重启。**不要**手动 `docker rm` + force-recreate。

**验证**：
```bash
docker compose exec -T backend alembic current   # 应显示 0170 (head)
docker compose exec -T backend python -c "import sqlalchemy" && echo ok
```
```sql
-- 新表/新列已就位
SELECT to_regclass('sentence_alignments'), to_regclass('alignment_candidates');
SELECT column_name FROM information_schema.columns
 WHERE table_name='alignment_pairs' AND column_name LIKE 'text_a_char%';
SELECT column_name FROM information_schema.columns
 WHERE table_name='mitra_alignments' AND column_name='mitra_e_score';
```
**部署后可用（有条件）**：跨语搜索 `GET /api/search/parallel-sentences` 与数据集导出 `GET /exports/alignments.jsonl`（chunk 级）**只在对应表已有数据时才有结果**。先确认 prod 存量——若为 0，跨语搜索要等 Phase 3b 导入、chunk 数据集要等 prod 已跑过 `build_alignments.py`：
```sql
SELECT (SELECT count(*) FROM mitra_alignments) AS mitra_rows,
       (SELECT count(*) FROM alignment_pairs)  AS chunk_pairs;
```

**回滚 ⚠️**：`docker compose exec -T backend alembic downgrade 0165`。
- 会 drop `sentence_alignments`(0170)、`mitra_e_score` 列(0169)、`alignment_pairs` 的 char 偏移列(0168)、`alignment_candidates`(0167)。
- **一旦跑过 Phase 3c（回填分数）或 Phase 4a（句级 refine），回滚就会毁掉这些算出来的数据**（需重跑，且重跑有 embedding API 成本）。干净回滚只在 Phase 2 之前。
- 0168 删掉的重复 embeddings 不随 downgrade 恢复——重跑 `scripts/repair_stale_embeddings.py` 再生。

---

## Phase 2 — 回填字符偏移锚点

**为什么**：`0168` 给 `alignment_pairs` 加了 `text_a/b_char_start/_end`（默认 NULL）。句级 refine（Phase 4）优先用这些偏移做**跨重分块稳定**的锚点；NULL 时回退到 `chunk_text`（降级但可用）。

**命令**：
```bash
# 先 dry-run 看定位率
docker compose exec -T backend python scripts/backfill_alignment_offsets.py --dry-run --limit 500
# 正式跑（幂等，只填 NULL 侧；分批 500/commit）
docker compose exec -T backend python scripts/backfill_alignment_offsets.py
```
**预期**：巴/藏侧因 `chunk_text` 存英译、原文在 `text_contents`，会报 `not_found`/`no_content` —— **属正常**，锚点先落汉文（lzh）侧。

**验证**：
```sql
SELECT count(*) FILTER (WHERE text_a_char_start IS NOT NULL) AS a_anchored,
       count(*) AS total FROM alignment_pairs;
```

---

## Phase 3 — MITRA 数据激活

### 3a. 许可确认 ⚠️（法务 Gate — 你拍板）

全量导入前，确认 **MITRA（CC-BY-SA-4.0）× CBETA（CC-BY-NC-SA）** 的 ShareAlike 叠加边界。见 `backend/docs/mitra-license.md` 与 `docs/legal/`。**未确认前不要跑 `--all`。** 现有 10 部试点经已在库，跨语搜索已能演示。

### 3b. 全量导入 ⚠️（~174 万行）

**Gate**：3a 已确认；`mitra-parallel` TSV 数据已下载到 VPS 某目录（数据集来自 [dharmamitra/mitra-parallel](https://github.com/dharmamitra/mitra-parallel)，arXiv:2601.06400，CC-BY-SA-4.0；把其 `tsv/` 目录路径给 `--mitra-dir`）。

```bash
# dry-run 先验定位率
docker compose exec -T backend python scripts/import_mitra_alignments.py \
  --mitra-dir /path/to/mitra-parallel/tsv --all --dry-run --log-every 25
# 正式全量（--skip-existing 可断点续跑；保护已回填的 mitra_e_score）
docker compose exec -T backend python scripts/import_mitra_alignments.py \
  --mitra-dir /path/to/mitra-parallel/tsv --all --skip-existing --log-every 25
```
**验证**：`SELECT count(*), count(DISTINCT taisho_id) FROM mitra_alignments;`

### 3c. 质量分回填 ⚠️（调 embedding API，有成本/耗时）

**为什么**：`mitra_e_score` 是 BGE-M3 cosine 代理分。回填后 RAG 的 MITRA 对读门（`enable_mitra_score_gate`，NULL 宽容）自动生效，跨语搜索排序也用它。

**前置**：确认 prod 的 embedding 端点已配（`embedding_api_url`/`embedding_api_key`）且能承压——这一步是百万级批量调用，上游限流会拖垮它。若指向共享上游，先确认配额/QPS。

```bash
# 断点续跑（只填 mitra_e_score IS NULL；每批 64 条 embed+写）
docker compose exec -T backend python scripts/backfill_mitra_scores.py --log-every 5000
```
⚠️ **成本预警**：~百万级行 × 每行两段文本的 embedding 调用。先 `--limit 1000` 试跑估算单位成本与吞吐，再放开全量；embedding 指本地 vLLM/上游按你的部署而定。

### 3d. 标定 `mitra_min_score`

⚠️ **先验证代理分是否有判别力**：`mitra_e_score` 是对**已被 MITRA 断言为平行**的两句算 cosine——已知平行句本就偏高 cosine，分布可能挤在高位、筛不出好坏。标定前先看分布：
```sql
SELECT width_bucket(mitra_e_score, 0, 1, 10) AS decile, count(*)
FROM mitra_alignments WHERE mitra_e_score IS NOT NULL GROUP BY 1 ORDER BY 1;
```
若绝大多数落在最高 1–2 桶，说明该代理分区分度差，`mitra_min_score` 门的实际价值有限（真正的语义质检要等 MITRA-E 9B，尚未接入）——此时更宜保持默认、不强行卡阈值。

```bash
# 导出分层标定样本 → 人工标注 ~200 对 → 定阈值
docker compose exec -T backend python scripts/backfill_mitra_scores.py \
  --export-calibration 500 /tmp/mitra_calib.jsonl
```
人工标注后选定阈值（默认 `0.30`），在 `.env` 设 `MITRA_MIN_SCORE=<值>` 并滚动重启。**标定完成前不要调高**——NULL 宽容门在回填前是 no-op，回填后按此阈值筛低质。注意：回填**进行中**时表内混有已评分/未评分行，门是部分生效的；等回填跑完再依赖它。

---

## Phase 4 — 句级对齐（护城河核心）

> **覆盖范围提醒**：`refine_sentence_alignments.py` 只遍历 `alignment_pairs`（curated chunk 对，量级 ~3千），**不**处理 MITRA 或全语料。因此 `sentence_alignments`、乃至将来的**阅读器逐句对读，只会在有 curated 对齐的那些经上亮，不是全站**。要扩覆盖，得先靠 Phase 5（margin 扩量）/ Phase 6（飞轮）把 chunk 级对齐做大，再重跑本步。

### 4a. 产出句级数据 ⚠️（调 embedding API）

**Gate**：Phase 2 已回填锚点（否则退化到 chunk 级切分，可接受但不理想）；embedding 端点可达（同 3c）。

```bash
# dry-run 看切句/对齐效果
docker compose exec -T backend python scripts/refine_sentence_alignments.py --dry-run --limit 50
# 正式跑（默认遍历 curated 的 alignment_pairs；方法可筛）
docker compose exec -T backend python scripts/refine_sentence_alignments.py \
  --method-filter embed_llm,manual,expert,flywheel-verified,embed_margin --log-every 50
```
**验证**：
```sql
SELECT count(*), count(DISTINCT source_pair_id) AS pairs_refined,
       align_type, count(*) FROM sentence_alignments GROUP BY align_type;
```

### 4b. 翻开 flag

确认 `sentence_alignments` 有数据后，在 `.env` 设：
```
ENABLE_SENTENCE_PARALLELS=true
```
滚动重启。此后 `GET /alignment/sentences/{text_id}/{juan_num}` 返回真实句对（此前是 dark，返回空）。

**回滚**：`ENABLE_SENTENCE_PARALLELS=false` 即时关闭，无需重新部署。

### 4c. ✅ 通知我建阅读器逐句对读 UI

`sentence_alignments` 有数据且端点返回非空后——**这一步招呼我**。届时我用真实数据建并验证前端逐句对读（char-offset 高亮 + 同步滚动，复用 `AlignmentColumn`/`useSyncScroll`），后端契约（Phase 4 已交付）现成。

---

## Phase 5 — margin 阈值标定（可与 Phase 3/4 并行）

**为什么**：`build_alignments.py` 的 margin 三带路由默认 **auto-accept 关闭**（逐条 LLM 验证，保 100% 精度）。标定后可开自动收，省 LLM 成本。

```bash
# 1) 建对齐质量金标集（人工确认 seed 标签后作为 gold）
docker compose exec -T backend python -m eval.build_alignment_gold --from-db \
  --per-kind 80 --seed 42 --out eval/alignment_gold.jsonl
# 2) 建回归基线
docker compose exec -T backend python -m eval.run_alignment_eval \
  --gold eval/alignment_gold.jsonl --scores-from-db --tag baseline
# 3) 在金标集上验证不同 --margin-accept 的 precision，选定后再用于挖矿：
docker compose exec -T backend python scripts/build_alignments.py --margin-accept <值>
```
把 `eval/run_alignment_regression.sh` 挂进现有每日 04:45 生产 cron（Telegram 告警链路复用，见 `fojin-eval-regression.sh`）。**在金标集上验证达标前不要下调 `--margin-accept`。**

---

## Phase 6 — 飞轮常态运行

挖候选 → 管理员在 `/admin/alignment/review` 人工复核 → accept 即以 `method='flywheel-verified'` 入 `alignment_pairs`。挖矿是 async service（`alignment_flywheel.py`），**没有 CLI/HTTP 包装**，用 python heredoc 触发（`mine_from_anchors` 精度优先，`mine_candidates` 高召回低精度慢，详见 [`ALIGNMENT_FLYWHEEL.md`](ALIGNMENT_FLYWHEEL.md)）：
```bash
docker compose exec -T backend python - <<'PY'
import asyncio
from app.database import async_session
from app.services.alignment_flywheel import mine_from_anchors
async def main():
    async with async_session() as db:
        n = await mine_from_anchors(db, limit=500, threshold=0.5)
        print("staged candidates:", n)
asyncio.run(main())
PY
```
适合挂夜间 cron（小 `limit`，让复核跟得上）。新入库的对齐会成为 Phase 4 下一轮 refine 的输入 —— 闭环。

---

## 附录：环境变量速查（`.env`，改后滚动重启）

| 变量 | 默认 | 作用 |
|---|---|---|
| `ENABLE_SENTENCE_PARALLELS` | `false` | 句级对读端点开关（Phase 4b 翻开） |
| `MITRA_MIN_SCORE` | `0.30` | MITRA 对读/搜索质量门阈值（Phase 3d 标定后设） |
| `ENABLE_MITRA_SCORE_GATE` | `true` | MITRA 质量门总开关（NULL 宽容，回填前 no-op） |

## 附录：整体验证查询

```sql
SELECT
  (SELECT count(*) FROM alignment_pairs)      AS chunk_pairs,
  (SELECT count(*) FROM sentence_alignments)  AS sentence_pairs,
  (SELECT count(*) FROM mitra_alignments)     AS mitra_pairs,
  (SELECT count(*) FROM mitra_alignments WHERE mitra_e_score IS NOT NULL) AS mitra_scored,
  (SELECT count(*) FROM alignment_candidates WHERE status='pending')      AS pending_review;
```

## 成本 / 耗时预期（先小样估算，勿盲跑全量）

| 步骤 | 主要成本 | 建议 |
|---|---|---|
| 3b 全量导入 | DB 写入 ~174 万行 | `--dry-run` 先验；`--skip-existing` 断点续跑 |
| 3c 分数回填 | embedding API（百万级行×2 段） | `--limit 1000` 估单位成本再放开 |
| 4a 句级 refine | embedding API（curated 段落切句） | 量级远小于 3c；`--dry-run --limit 50` 先看效果 |
