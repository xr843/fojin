# Embedding `text_embeddings.juan_num` 标注 Bug 调查
**Date**: 2026-05-08
**Scope**: 只读分析，无 SQL 写入、无代码改动
**Source**: fojin 生产 PG (sg-vps `100.67.232.7`, container `fojin-postgres`, db `fojin`)

---

## 1. 影响面

### 总体（按 `juan_num=1` 容量超限定义 bug）
| bucket | texts | chunks | 说明 |
|---|---|---:|---|
| 1_juan_text_ok | 7609 | 272186 | 单卷经，j1 必正确 |
| plausible | 1163 | 304260 | 多卷经，j1 chunks 数量在卷1 char_count 容量内 |
| **BUG_j1_overflow** | **118** | **69731** | **多卷经，j1 chunks 远超卷1 字数应有量** |
| no_j1 | 64 | 31927 | 多卷经里无任何 j1 chunk（异常但非本 bug） |

### 量化错标 chunks 数
对多卷经计算 `j1_chunks - ceil(j1_chars / 150)`（150 字/chunk 是合理上限），得到：

- **多卷经里 juan=1 总 chunks = 52,667**
- **其中 mislabeled (超容量) ≈ 17,417 chunks**
- 占全库 chunk 比例: 17417 / 678112 = **2.57%**
- 占多卷经 chunk 比例: 17417 / 405,926 ≈ **4.3%**

### 第二 bucket：`partial_loss` 46 texts
te 中 distinct juan 数 < tc 中 distinct juan 数，即少数后段卷完全没生成 embedding。这是另一个独立问题（可能是 import_content 部分卷漏 ingest 或 generate_embeddings 中断），与本调查的 j1 错标 bug **机制不同**，但应作为后续 follow-up（已列出 top 15 受影响经，最大 T1828 瑜伽論記 缺 1 卷 / 3173 chunks）。

---

## 2. 抽样验证（确认 bug 真实存在）

| taisho | title | tc 卷数 | te 卷数 | 总 chunks | j1 chunks | pct_j1 | j1_chars (卷1) | 备注 |
|---|---|---:|---:|---:|---:|---:|---:|---|
| T1579 | 瑜伽師地論 | 100 | 100 | 4462 | **1135** | 25.4% | 8,433 | 卷1只 8K 字却装 1135 chunks |
| T1912 | 止觀輔行傳弘決 | 12 | 12 | 1468 | **1123** | 76.5% | 64,196 | 76% chunks 全堆 j1 |
| T1716 | 妙法蓮華經玄義 | 12 | 12 | 823 | 533 | 64.8% | 20,128 | |
| T0293 | 大方廣佛華嚴經 | 40 | 40 | 1414 | 709 | 50.1% | 6,386 | |
| T1851 | 大乘義章 | 22 | 18 | 2487 | 388 | 15.6% | 40,640 | 同时有 partial_loss |

**铁证 1（T1579 chunk_index=60, juan=1）**：chunk_text 含"分中有尋有伺等三地..."，但 SQL 反查 text_contents 显示该字符串只出现在卷 4-8，绝不在卷 1（卷 1 是"五識身相應地"）。

**铁证 2（T1579 chunk_index=151, juan=1）**：chunk_text 末尾出现 `瑜伽師地論卷第八` + `瑜伽師地論卷第九` 两个卷标记 —— 该 chunk 跨越 juan 8/9 边界，绝不可能是卷 1 内容。

**铁证 3（T1851 chunk_index=200, juan=1）**：chunk_text 含"四中以何義故偏名滅諦"，反查 text_contents 该字符串只出现在卷 3。

---

## 3. 根因

**根因不在当前 ingestion 代码**，而是 **遗留数据 + 增量补 ingest 跳过策略**两个 bug 的交互。

### 时间线证据
按 `text_embeddings.created_at` 分桶：
```
2026-03-19 / 03-20 / 03-23  →  早期大批 ingest（122k + 224k + 72k chunks）
2026-04-01 / 04-02           →  CBETA full reimport（146k + 110k chunks）
```

T1579 各卷 chunk 创建时间：
- juan_num=1 的 1135 chunks: **2026-03-19** 单一时间戳
- juan_num=2..100 的 chunks: **2026-04-01** 单一时间戳

→ juan=1 的 1135 chunks 是 3-19 老 ingest 留下的，4-1 reimport 没动它们。

### 上游 parser bug（已修复）
`backend/app/core/xml_parser.py` —— commit `ae19776` (2026-03-29)
> `fix(import): remove cb:div from CONTENT_TAGS to fix missing juans`
>
> "cb:div was in both CONTENT_TAGS and the container element list. Since CONTENT_TAGS is checked first, cb:div elements were treated as leaf content (extracting text + return) instead of being recursed. This caused milestone markers inside cb:div to be skipped, resulting in missing juans"

3-29 之前 parser 把 `<cb:div>` 当 leaf → 跳过内部的 `<cb:juan>` milestone → **整本书的所有卷被合并成第一个 `juan_num=1` 的 record**。3-19/3-20 ingest 用的就是这个 buggy parser。

### 写入 PG 的代码（无 bug）
`backend/scripts/generate_embeddings.py`:
- L48 `chunks = chunk_text(tc.content, chunk_size=500, overlap=50)`
- L82 `"juan_num": tc.juan_num`

代码本身忠实地用 `tc.juan_num`，但当时 `tc` 已经是错的（整本书塞进 juan=1）→ chunker 切出的 1135 chunks 全部继承 `juan_num=1`。

### 增量补 ingest 的回填漏洞
`generate_embeddings.py` L31-32 + L38-42 + L78：
```python
"CREATE UNIQUE INDEX ... ON text_embeddings (text_id, juan_num, chunk_index)"
async def get_existing_chunks(session, text_id, juan_num):
    "SELECT chunk_index FROM text_embeddings WHERE text_id=:tid AND juan_num=:jn"
"INSERT ... ON CONFLICT (text_id, juan_num, chunk_index) DO NOTHING"
```

3-29 parser 修复 + 4-1 重 import_content 把 `text_contents` 拆成 100 卷后，4-1 重跑 generate_embeddings 时：
1. 对 juan=1 调 `get_existing_chunks` → 已有 1135 chunks，**全部跳过**（旧错数据未清理）
2. 对 juan=2..100 → 没有任何 chunks → 新生成（正确）

→ juan=1 的旧污染数据被永久保留，新数据并排共存。

---

## 4. 修复方案

### 方案 A：完全重 embed 受影响 texts
1. `DELETE FROM text_embeddings WHERE text_id IN (118 BUG_j1_overflow texts) AND juan_num=1`
2. 重跑 `generate_embeddings.py --filter` 仅这些 texts
3. 由于 unique index + ON CONFLICT DO NOTHING，需要先 DELETE 否则跳过

**成本估算**:
- 受影响 j1 chunks: **52,667** (含 35,250 正确 + 17,417 错标)
- 全删后重生成: ~52,667 chunks
- DeepSeek embedding 单价（按 memory `project_fojin_deepseek_v4_switch.md` 现走 v4-pro 75% 促销）→ embedding API 通常按 token 计价：每 chunk ~500 字 ≈ 800 token，52667 × 800 = ~42M tokens
- 按 BGE-M3 / 现用 embedding provider 估 ¥0.5-2 / 1M tokens → **¥20-80**
- 时长: EMBED_BATCH_SIZE=20，按 ~1s/batch → ~45 分钟
- 风险: ingest 期间 RAG 短暂缺该 118 texts 的 j1 部分 → 建议**off-peak**跑（凌晨 3-5 点）

### 方案 B：廉价回填（仅 UPDATE juan_num，复用 embedding）
利用 chunk_text 内容反查 text_contents.content 的真实 juan_num：

```sql
-- 伪代码（实际需 Python 脚本，因 SQL 字符串匹配性能差）
UPDATE text_embeddings te
SET juan_num = (
    SELECT tc.juan_num FROM text_contents tc
    WHERE tc.text_id = te.text_id
      AND tc.content LIKE '%' || substring(te.chunk_text, 1, 50) || '%'
    ORDER BY juan_num LIMIT 1
)
WHERE te.text_id IN (118 受影响 texts) AND te.juan_num = 1;
```

**成本估算**:
- ¥0 — 不调 embedding API
- 需新写一次性脚本（~1 小时编码）
- 跑 17,417 chunks × LIKE 全文 → 多卷经平均 100 卷 × 8K chars，需建 trgm 索引或在 Python 中做 substring match
- 跑时长: ~30 分钟（带索引），~3 小时（不带）
- 限制:
  - chunk 跨 juan 边界（如 T1579 chunk_index=151 含卷 8 末 + 卷 9 头）→ 选 first match 的 juan，会漏标卷 9 部分。可接受（比错标卷 1 好）
  - chunk_text 头部 50 字若是空白/常用语（"復次"、"佛言"）→ 误匹配。需取较长 distinctive substring（建议 100 字 + 跳过纯标点）
  - chunker `overlap=50` → 邻接 chunks 头部重复，但因为按 LIKE 第一 match 取 juan，影响有限

### 推荐：**方案 B**

理由：
1. **零 token 成本**，无 budget 顾虑（memory `project_fojin_deepseek_spike_20260416.md` 说明对 token 成本敏感）
2. embedding 向量本身用 chunk_text 生成，与 juan_num 标注无关 → 复用是安全的
3. 准确性可达 ~95%+（仅跨 juan 边界 chunk 边缘 case 受限），远好于现状 ~25-76% 错标率
4. 失败可回退（更新前 SELECT 出 (id, old_juan, new_juan) 备份到临时表）
5. 4-6 周内若有大改 chunker 策略，方案 A 都得重跑；方案 B 是廉价过渡

**实施步骤建议**（不实施，仅设计）：
1. 一次性 Python 脚本 `backend/scripts/fix_juan_num_misattribution.py`
2. 锁定 118 texts 范围（从 `BUG_j1_overflow` bucket 查询得出）
3. 对每个 chunk 做 `text_contents.content LIKE` 反查，取 distinct juan_num
4. dry-run 模式输出 (text_id, chunk_index, old_juan, new_juan) CSV 让人 review 100 行抽样
5. 加 trgm 索引: `CREATE INDEX text_contents_content_trgm ON text_contents USING gin (content gin_trgm_ops)` (临时，跑完 DROP)
6. 批量 UPDATE，commit 后跑相同的影响面 SQL 验证 BUG_j1_overflow → 0
7. 写一份 audit log: `text_id, chunks_fixed, old_juan_distribution, new_juan_distribution`

### 顺带处理 partial_loss bucket（46 texts / 28667 chunks）
正交问题，但建议同期跑：核对 `text_contents` 是否每卷齐全，对缺卷补 import + generate_embeddings —— 这部分**必须**用方案 A（生成新 embedding），但量小（28k chunks，~¥10-30）。

---

## 5. 用户感知影响

### Citation 卷号错误率
- **多卷经查询命中错 chunk 概率**: 17417 / 405926 = **4.3%**
- 加权用户实际感知率（多卷经查询占总查询 ~70%，单卷经天然不受影响）→ ~3% 引用卷号显示错
- 集中在重要论藏类经典（瑜伽論、大乘义章、大涅槃義記等）—— 这些恰是学术用户最可能引用的
- 76.5% 错标的 T1912（止观辅行）单部经 citation 几乎**不可信**

### Telemetry
- `reading_history` 表只有 (user_id, text_id, juan_num) 单条 unique，不记跳转事件，无法直接量化"用户点了 citation 跳错卷"
- 建议: 后续可临时加 backend log "citation_click" event（不属本调查范围）

### 紧迫性
- 不是 P0：embedding 向量本身没错，语义召回正确；只是显示的"出自卷 X"卷号错
- P1：影响学术信任度。FoJin 定位是学术辅助工具（memory `project_fojin_trilingual_rag_mvp.md`），错引卷号会被引用者发现
- 建议: 与 `project_fojin_chat_input_v2.md` PR-B/C 同期排进 sprint，不阻塞主路径但 4-6 周内修

---

## 附录: 关键 SQL（已跑，仅 SELECT）

```sql
-- 影响面
WITH stats AS (SELECT te.text_id,
  SUM(CASE WHEN te.juan_num=1 THEN 1 ELSE 0 END) AS j1_chunks,
  COUNT(*) AS total_chunks
  FROM text_embeddings te GROUP BY te.text_id),
tc AS (SELECT text_id, COUNT(DISTINCT juan_num) AS tc_juan
  FROM text_contents GROUP BY text_id),
tc1 AS (SELECT text_id, char_count AS j1_chars
  FROM text_contents WHERE juan_num = 1)
SELECT
  CASE
    WHEN tc.tc_juan = 1 THEN '1_juan_text_ok'
    WHEN s.j1_chunks > (tc1.j1_chars / 150.0) * 1.5 THEN 'BUG_j1_overflow'
    WHEN s.j1_chunks > 0 THEN 'plausible'
    ELSE 'no_j1'
  END AS bucket,
  COUNT(*) AS texts, SUM(s.total_chunks) AS chunks
FROM stats s JOIN tc USING(text_id) LEFT JOIN tc1 USING(text_id)
GROUP BY 1;

-- 错标量化
SELECT SUM(GREATEST(s.j1_chunks - CEIL(tc1.j1_chars / 150.0)::int, 0)) AS suspect_misjuan
FROM stats s JOIN tc USING(text_id) LEFT JOIN tc1 USING(text_id)
WHERE tc.tc_juan > 1;
-- = 17417

-- 时间线确认
SELECT juan_num, MIN(created_at), COUNT(*)
FROM text_embeddings WHERE text_id = 43 GROUP BY juan_num ORDER BY juan_num;
-- juan=1 → 2026-03-19, 1135
-- juan=2..100 → 2026-04-01, 17-22 each
```
