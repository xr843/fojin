# 跨藏对齐质量评测 (alignment-quality eval)

把三个对齐存储的质量从「MVP 样本人工看过」变成可度量、可回归的数字。与答案质量评测
（`eval/README.md`）同一套打法：**指标逻辑纯函数 + CI 单测护住；全量评测跑在能连 prod DB 的
地方（cron）；对照 baseline 非零退出做门**。

| 存储 | 规模 | 现有"质量分" | 问题 |
|------|------|--------------|------|
| `alignment_pairs` | ~3,170 chunk 对 | `confidence`（构建时 LLM verifier 的信心，≥0.75 才入库） | 只有被接受的对；拒绝候选没落库 → 库内无负例，精确率量不出来 |
| `mitra_alignments` | ~896K 句级对 | `confidence` 恒为 1.0（导入标志）；`mitra_e_score` 回填中 | 回填完成前分数无信息量 |
| `text_relations` | 经级 parallels | `confidence`（SuttaCentral/Akanuma 导入值） | 从未对照人工标注校验 |

因此评测需要一个**独立的黄金集**：人工确认的正例 + **构造的**负例（存储里没有负例可采）。

## 黄金集格式（JSONL，一行一条）

```jsonc
{
  "record_id": "ap-12345",          // 唯一 id。builder 约定：ap-<id> / ma-<id> / tr-<id>（对应存储主键）、
                                    // neg-shifted-… / neg-crosstext-…（构造负例）、syn-…（合成样例）
  "source": "alignment_pairs",      // alignment_pairs | mitra_alignments | text_relations
                                    //（构造负例继承其种子正例的 source）
  "source_row_id": 12345,           // 存储主键；构造负例为 null。--scores-from-db 靠它取分
  "granularity": "chunk",           // chunk | sutta（text_relations 是经级）
  "pair_kind": "zh-pi",             // zh-pi | zh-bo | zh-sa | zh-en（方向归一，zh 在前）
  "side_a": {                       // chunk 级引用：{text_id, juan_num, chunk_index, lang, text?}
    "text_id": 2, "juan_num": 24, "chunk_index": 5, "lang": "zh",
    "text": "……"                    // 可选内联片段，方便人工审核
  },
  "side_b": {                       // 同上；MITRA 式行的外语侧只有内联文本：{text, lang}
    "text": "kāye kāyānupassī …", "lang": "pi"
  },                                // sutta 级：{text_id, lang}，无 juan/chunk
  "label": true,                    // true = 平行；false = 非平行
  "label_source": "human",          // human = 人工确认过；seed_verified = 机器产出（种子管线接受的
                                    // 正例 / 构造的负例），**尚待人工确认**
  "negative_kind": null,            // 仅负例：shifted | cross_text | near_neighbor；
                                    // 人工判否的存量行（非构造）用 null
  "note": "自由文本"
}
```

校验规则在 `eval/alignment_metrics.py::validate_gold_record`（runner 载入时强制执行，坏记录
**整次失败**而不是静默丢弃）。`eval/alignment_gold.sample.jsonl` 有 10 条**合成**样例，覆盖全部
字段组合——仅演示格式，**不要**当真实标注用。

### 负例三兄弟

| negative_kind | 构造方式 | 难度 | 状态 |
|---------------|----------|------|------|
| `shifted` | 同一文本对，side_b 的 chunk_index 相对已知正例偏移 ±1/±2 | 硬（相邻 chunk 常延续同段义理，甚至可能真平行——所以必须人工过） | builder 自动生成 |
| `cross_text` | side_b 换成一篇**无关**文本的 chunk（排除任何存储里相关的文本对） | 软（锚定校准表底部） | builder 自动生成 |
| `near_neighbor` | 同一文本对里 embedding 余弦高但**非**平行的 chunk | 最硬、最有价值 | **TODO** — 挖掘需要 embedding API 排序候选，离线 builder 不调 API；格式已预留 |

## 在 prod 上构建黄金集

```bash
# 方式一：从数据集导出构建（只有正例，无需 DB）
python -m scripts.export_alignment_dataset --out /tmp/fojin_alignments.jsonl
python -m eval.build_alignment_gold --from-export /tmp/fojin_alignments.jsonl --per-kind 50 --seed 42

# 方式二：直连 DB，三个存储分层采样 + 自动构造负例（推荐）
python -m eval.build_alignment_gold --from-db --per-kind 50 --seed 42 \
    --shifted-per-positive 1 --cross-per-positive 1
# → eval/reports/alignment-gold-candidates-<时间戳>.jsonl
```

`--seed` 决定采样、负例构造与输出乱序——同 seed 完全可复现。`--per-kind` 每个语言对最多取 N 条
正例（防止 mitra 的 896K 行淹没 3K 精标对）。

**产出是候选，不是黄金集。** 所有 `label_source: "seed_verified"` 的记录（种子正例 **和** 构造负例）
都要人工过一遍：正例确认真平行（不是就把 `label` 改 `false`、`negative_kind` 留 `null`）；`shifted`
负例尤其要看——相邻 chunk 有时真的平行，是就改 `label: true`。确认后把 `label_source` 改成
`"human"`，把文件存为 `eval/alignment_gold.jsonl`（bind mount 下宿主机可见，建议入库版本管理）。
**没过人工的候选直接当门用，等于让管线自己给自己打分。**

## 预测分从哪来（predictions JSONL：`{"record_id": "...", "score": 0.87}`）

| 模式 | 需要什么 | 度量什么 |
|------|----------|----------|
| `--scores-from-db` | 只要 DB | 存量分数的**校准**：`alignment_pairs.confidence` / `mitra_alignments.mitra_e_score`（列不存在或未回填时退回 `confidence`，即恒 1.0，报告会警告）/ `text_relations.confidence`。**构造负例库里没有行，取不到分**——此模式下 precision 只反映「存量分数 vs 人工判否的存量行」，覆盖率会明说 |
| 重跑 LLM verifier | LLM key | 真精确率/召回：对黄金集每条（含构造负例）取双侧文本，走 `scripts/build_alignments.py` 的 `llm_verify_pair` 同款 prompt，把 `confidence` 写成 predictions JSONL。烧 token，低频跑 |
| embedding 余弦 | embedding API | 廉价 proxy：双侧向量余弦作 score。适合大批量粗校准 |

后两种是标准的「重打分」流程：读黄金集 → 按 `side_a`/`side_b` 取文本（chunk 引用查
`text_embeddings.chunk_text`，内联文本直接用）→ 打分 → 落 JSONL。写成脚本后可与
`--predictions` 对接；本仓库刻意不内置（避免离线环境的 API 依赖）。

## 运行评测

```bash
cd backend
python -m eval.run_alignment_eval --gold eval/alignment_gold.jsonl --scores-from-db
python -m eval.run_alignment_eval --gold eval/alignment_gold.jsonl \
    --predictions /tmp/alignment_scores.jsonl --threshold 0.75 --tag nightly
```

报告写到 `eval/reports/alignment-eval-<时间戳>-<tag>.md`（+ 同名 `.json` 原始指标，供
`--baseline` 对照）。内容：阈值处 P/R/F1 + 混淆计数、全阈值扫描（0.00–1.00 步长 0.05）、
校准表（预测分十分位 → 实测精确率）、分片（语言对 / 存储 / 标注来源 / 负例构造方式的误报率）。
指标口径与 `retrieval_metrics` 一致：分母为空记 `None` 不记 0，聚合与门都跳过 `None`。

> 报告目录权限同 run_eval：容器 `app(999)` 写宿主 `admin(1000)` 目录失败时退到 ephemeral 的
> `/tmp` 并打印警告。修复：`chgrp 999 backend/eval/reports && chmod g+w backend/eval/reports`

## 回归门（与 `run_eval.py` 同一套约定）

```bash
# 生成基线（有意的质量变更后重新生成，raw json 存为 baseline）：
python -m eval.run_alignment_eval --gold eval/alignment_gold.jsonl --scores-from-db --tag baseline
cp eval/reports/alignment-eval-<ts>-baseline.json eval/reports/alignment-baseline.json

# 门：对照基线，precision / recall / f1 / prediction_coverage 跌超容差即非零退出
python -m eval.run_alignment_eval --gold eval/alignment_gold.jsonl --scores-from-db \
    --baseline eval/reports/alignment-baseline.json \
    --fail-on-regression --regression-tolerance 0.02
# 绝对下限：
python -m eval.run_alignment_eval --gold ... --scores-from-db --min-precision 0.90
```

与 `run_eval.py` 完全同构的语义（cron shim 的告警逻辑零改动即可复用）：

- **退出码**：门失败（回归 / 低于下限 / baseline 读不了且 `--fail-on-regression`）→ `exit 1`；
  其余 `exit 0`；输入文件缺失/损坏 → 异常非零退出。
- **baseline 读不了 ≠ 无回归**：`--fail-on-regression` 下算门失败（run_eval 踩过的坑，这里直接继承）。
- `prediction_coverage` 也在被门的指标里：打分覆盖率悄悄下降（比如负例全部失去分数）会被当回归抓出来，
  而不是让 precision 虚高地绿灯。
- 门内含阈值一致性检查：当前与 baseline 的 `--threshold` 不同会直接报为回归（苹果比橘子）。

门逻辑版本化在 **`eval/run_alignment_regression.sh`**（同 `eval/run_regression.sh` 的存在理由）：

```bash
# 在 backend 容器内（cwd /app）：
eval/run_alignment_regression.sh
ALIGN_GOLD=... ALIGN_BASELINE=... MIN_PRECISION=0.90 TOLERANCE=0.03 eval/run_alignment_regression.sh
```

### ops：接入日常 cron（不要改 `fojin-eval-regression.sh` 本体）

`fojin-eval-regression.sh` 的门命令本来就通过 `EVAL_GATE_CMD` 注入，告警/退出码透传逻辑可原样
复用。在 VPS 上加一个瘦 shim + 一条 cron 即可（与现有 `fojin-eval-gate.sh` 同款做法，凭据留 host）：

```bash
# /home/admin/fojin-alignment-gate.sh （VPS-only，chmod +x）
#!/usr/bin/env bash
source /home/admin/fojin-telegram-creds.sh   # 导出 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID（同现有 shim）
export EVAL_GATE_CMD='docker compose exec -T backend eval/run_alignment_regression.sh'
exec /home/admin/fojin/fojin-eval-regression.sh
```

```cron
# crontab -e (admin)——错开检索门的 04:45：
55 4 * * * /home/admin/fojin-alignment-gate.sh >> /home/admin/fojin-alignment-gate.log 2>&1
```

> 告警文案会沿用「答案质量回归门失败」前缀，但 tail 里带的是对齐评测的具体回归行，可区分。
> 想要独立文案再考虑改 `fojin-eval-regression.sh`（本次刻意不动它）。

## 当前局限（读数前先看）

1. **`--scores-from-db` 量的是校准不是精确率**：构造负例没有库内分数，不进混淆矩阵。真精确率
   要走「重跑 LLM verifier」的重打分流程。runner 对此会打印明确警告 + 覆盖率。
2. **mitra 侧分数暂无信息量**：`mitra_e_score` 回填完成前退回恒 1.0 的 `confidence`，校准表会
   坍缩到最高分桶——这是数据现状的忠实呈现，不是 bug。回填后无需改代码，自动改用 `mitra_e_score`。
3. **seed 正例未经人工确认前不是 ground truth**：门在此期间量的是「相对基线的漂移」，不是绝对精度。
   人工确认的比例应逐步提高（`label_source` 分片专门用来盯这个）。
4. **`near_neighbor` 负例未实现**（需要 embedding API 挖掘）；`shifted` 是当前最硬的负例，但覆盖
   不了「语义近邻假平行」这一失败模式。
5. **MITRA 内联行没有构造负例**：外语侧是内联文本、没有 fojin chunk，shifted/cross_text 都无从构造
   （builder 会跳过）。mitra 侧的负例目前只能来自人工判否的存量行；廉价的未来扩展是把两条相距很远的
   mitra 行互换 `foreign_text` 作 cross_text 负例。
6. **黄金集是静态采样**：新增对齐批次（如 25k 般若分卷跑完）后应重建/扩充黄金集并重新生成 baseline，
   否则新批次的质量不在度量范围内。

## 文件

- `alignment_metrics.py` — 确定性指标纯函数：P/R/F1、阈值扫描、校准、分片、回归检测（CI 单测
  `tests/test_alignment_metrics.py`）
- `build_alignment_gold.py` — 黄金集候选构建：导出/DB 两种模式 + shifted/cross_text 负例构造
  （纯逻辑 CI 单测 `tests/test_build_alignment_gold.py`）
- `run_alignment_eval.py` — 载入黄金集+预测 → 指标 → 报告 → 回归门（CLI 行为 CI 单测
  `tests/test_run_alignment_eval.py`）
- `run_alignment_regression.sh` — 版本化的 cron 门包装
- `alignment_gold.sample.jsonl` — 10 条合成格式样例（**非**真实标注）
- `ALIGNMENT_EVAL.md` — 本文件
