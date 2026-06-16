# 跨藏对照触达改造 — 设计文档 (Cross-Canon Surfacing, Slice A)

- **日期**: 2026-06-16
- **状态**: 待评审 (Draft)
- **范围**: 第一切片(Approach A：沿旅程立路标）。不含专属 Hub 落地页(留作后续 B）。

## 1. 背景与目标

fojin 的核心护城河是**跨藏对照**——把同一作品/段落在汉/梵/藏多藏经间互链，可被 AI 跨语调用。MITRA-E vs BGE-M3 实测(2026-06-16)证明这条护城河的底座是真的强(MITRA-E 跨语分离度 99.2%)。但**护城河被埋着**：

- 唯一已存在的发现入口 `/api/alignment/catalog`(#693）**只聚合 `alignment_pairs`**(~4099 条 LLM 验证对、约 10 部经），**完全没包含 `mitra_alignments` 那 90 万对(~1018 部经)**。即：现有发现页只展示了真实跨藏覆盖的**约 1%**。
- 自然浏览路径上缺少路标：`TextDetailPage` 只有作品级「其他版本」(`OtherVersions`，走 works/witnesses)，**没有段级跨藏对照入口**；reader 的「跨藏对照」是众多控件里的一个 toggle(`TextReaderPage.tsx:740`)，不显示有无/段数；搜索结果不标注「此经有平行」。

**目标**：让"这段经文有跨语平行"成为搜索/阅读路径上的一等信号，把 ~1018 部经的真实跨藏覆盖暴露出来，形成 **搜索发现 → 文本确认 → 面板探索** 的连贯旅程。**核心论点**：用户找得到的、稍有噪声的跨语网，价值远高于完美清洗但没人找得到的。

## 2. 非目标 (Out of Scope)

- 专属跨藏 Hub 落地页(Approach B，留作 A 验证有人点穿后的第二步)。
- 对照面板(`ReaderParallelPanel`)内部渲染逻辑改造。
- 实时跨语义搜索(需在线 MITRA-E，已决定不做)。
- 修 `/activity` 的 Source-Updates 数据管道(单独议题)。

## 3. 设计

### 3.1 地基:扩展 `/api/alignment/catalog`(必做，其余依赖它)

当前 catalog SQL 只聚合 `alignment_pairs`。把 `mitra_alignments` 纳入。**✅ 已实现并生产验证**(`backend/app/api/alignment.py`)。

- **⚠️ 性能实测纠错(关键)**：一开始把两源合到**单条 UNION + `GROUP BY` 带 `mode()`/`count(DISTINCT)`/`array_agg(DISTINCT)` + JOIN buddhist_texts** —— 生产实测 **76.7 秒**，远超应用 `statement_timeout=30s`，**端点会被杀**。根因不是 mitra 量大(纯 `count GROUP BY` 仅 2.8s、带 `mode(juan)` 7.4s),而是 90 万行先 JOIN + DISTINCT/array_agg。
- **正解(已落地)**:**两源分开聚合 → Python 合并 → 缓存**。
  - fojin 侧:原查询(`alignment_pairs`,~4099 行,带 partner/distinct/mode,快)。
  - mitra 侧:`SELECT text_id, foreign_lang, count(*), mode() WITHIN GROUP (ORDER BY juan_num) FROM mitra_alignments GROUP BY ...`(**无 join/distinct/array_agg**,~7s,在 30s 超时内)。
  - 按 `(text_id, other_lang)` 合并:`pair_count` 相加;`sources` 取并(fojin/mitra);`sample_juan` 优先 fojin(有锚点);partner 仅 fojin。
  - **Redis 缓存最终结果**(key `alignment:catalog:v2`,TTL 1800s;mitra 覆盖只在 import/backfill 变)。冷缓存 ~7s 在超时内,且很少命中。
- 响应模型 `CatalogEntry` 增 `sources: list[str]`,`avg_confidence`/`sample_partner_id` 改可空(mitra-only 无 partner、confidence 无意义)。向后兼容。
- **深链卷**:`sample_juan`(mitra 取 `mode(juan_num)`)作 3.3a 深链目标卷;退化首卷。
- **质量过滤预留**:mitra 查询处留注释,`mitra_e_score` 回灌后加 `WHERE mitra_e_score >= 0.30`。上线初期不过滤(计数轻微偏高无害)。
- **生产验证**:覆盖 ~10 → **1016 部经 / 900,301 段**;语法+ruff 通过。

### 3.2 并行轨:离线 MITRA-E 全量打分(现在启动)

- **为什么并行而非阻塞**：`mitra_alignments.confidence` 默认全 = 1.0(仅导入置信，非质量分)，故**没有 `mitra_e_score` 就无法滤掉 90 万里那 1-4% 噪声**。要把跨藏曝光给学者，必须有这个质量分。
- 流程：导出 896K → 本地 A6000 跑 MITRA-E(`<instruct>` query + last-token + L2，方法见 `project_fojin_mitra_e_benchmark`)→ 加 `mitra_alignments.mitra_e_score` 列(alembic migration)→ 回灌。预计 ~7–13h 过夜任务，读-only 不影响线上。
- 阈值(已在 2万样本验证)：`<0.30` 自动排除(~0.7%/~5.8K，深在噪声区)；`0.30–0.40` 降权/标记。catalog(3.1)启用 `mitra_e_score >= 0.30` 过滤。
- **前端不阻塞**：3.3 的路标可先按全量计数上线，分数回灌后 catalog 自动变干净。

### 3.3 三个前端路标(都读 3.1 的 catalog)

复用现有 react-query `["alignmentCatalog"]`(`CollectionsPage` 已用)；前端拉一次 catalog 当"哪些经有平行"的全量索引，就地判断成员资格。

- **a. 文本详情/阅读器路标(黄金发现点)**
  - `TextDetailPage`：在 `OtherVersions`(作品级)旁**新增**段级跨藏入口卡：「本经有 N 段 藏/梵 跨藏对照 →」(N、语种来自 catalog)。点击 → reader 的对照视图，定位到平行段最多的卷(catalog 已有此信息或退化到首卷)。这是与 `OtherVersions` 互补的**新信号**(作品级 vs 段级)。
  - `TextReaderPage`:给现有「跨藏对照」按钮(`:740`)加**有无/段数徽章**，让用户不点也知道有料。
- **b. 搜索结果徽章**
  - `UnifiedResults`/`ResultCard`/相关 card：若 `hit.text_id` ∈ catalog → 加「藏·梵 对照」徽章 + 点击去对照视图。区别于现有 `CrossLangCard`(那是"跨语命中"结果，本徽章是"此汉文经有平行可读")。
- **c. `/collections` 跨藏专区升为一等入口(不建新页)**
  - 把现有跨藏专区(`CollectionsPage.tsx:205+`)**置顶**；
  - 加 **nav 入口** + **首页 feature 卡**直接指向它(锚点或 query param)。
  - 真正的独立落地页延后到 B。

### 3.4 捎带:隐藏页回归导航

`frontend/src/components/Layout.tsx:82-88` 取消注释：

- **dashboard + timeline**：完整可用，直接放回。
- **activity**:学术 tab + 平台统计可用，但 **Source-Updates 子标签无数据流**——先**隐掉该空子标签**再放回 activity，不暴露半成品。

### 3.5 工程约束

- **i18n**：所有新文案(徽章、路标卡、nav label、入口卡)走 i18n locale key(zh / zh-Hant / en)，否则撞 CI `scan-hardcoded-zh` ratchet。插值用 `{{n}}` 不用 `{{count}}`。
- **缓存一致性**:catalog 改数据(清洗回灌)后需失效 Redis key。
- **部署**:alembic migration(`mitra_e_score` 列) + backend(catalog) + frontend(路标)；按 `feedback_fojin_alembic_chain_check` 先核 prod alembic head。

## 4. 数据流

```
mitra_alignments (896K) + alignment_pairs (4099)
        │  GROUP BY lzh text_id, lang  (+ mitra_e_score>=0.30 once backfilled)
        ▼
/api/alignment/catalog  ──Redis cache──▶  前端 ["alignmentCatalog"] 一次拉取
        │                                        │
        │                          ┌─────────────┼─────────────┐
        ▼                          ▼             ▼             ▼
  CollectionsPage 置顶        TextDetailPage   搜索结果徽章   reader 按钮徽章
  (一等入口 c)               入口卡 (a)        (b)          (a)
                                   │
                                   ▼  点击
                          reader 对照视图 / ReaderParallelPanel (已有，定位到平行最多卷)
```

## 5. 依赖与排期

1. **现在并行启动**：3.2 离线全量打分(过夜)。
2. 3.1 catalog 扩展(后端) → 3.3 路标(前端)依赖它。
3. 3.4 nav 回归、3.3c 置顶可独立先行(不依赖打分)。
4. `mitra_e_score` 回灌后启用 catalog 质量过滤(3.1)。

## 6. 成功标准

- catalog 覆盖从 ~10 部 → ~1018 部经(API 实测)。
- 从搜索结果 / 文本详情 / 首页，**≤2 次点击**可达某经的跨藏对照视图。
- 路标只在真有平行时出现(零误报：catalog 成员判断准确)。
- 全程零新增硬编码中文(ratchet 绿)；catalog p95 延迟不退化(缓存命中)。
- 清洗回灌后，catalog 计数反映 `mitra_e_score>=0.30` 的干净覆盖。

## 7. 测试

- 后端：catalog union 的 SQL 单测(含 mitra-only、fojin-only、两者皆有的经)；缓存命中/失效。
- 前端:catalog 成员判断的单测;徽章/入口卡在"有/无平行"两态渲染;i18n 三语 key 齐。
- E2E：搜索 → 徽章 → 对照视图 一条 Playwright spec(对 prod，复用现有 e2e/)。

## 8. 待评审决策点

- catalog 质量过滤上线初期是否就启用(取决于 `mitra_e_score` 回灌时机 vs 前端上线时机)。
- reader 按钮徽章 vs 文本详情入口卡，是否两个都做还是先做文本详情(黄金点)。
- `/collections` 跨藏专区置顶的 nav label 文案 + 是否独立 query param。
