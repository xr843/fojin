# 阅读器逐句对读（Reader Sentence-Level Parallel Reading）设计

**日期**：2026-07-11
**状态**：设计已批准（用户将 spec 审核权委托给实施方）
**背景**：对齐层 Phase 4 的收尾前端。后端契约（P4-C，PR #966）已就绪且冻结；本设计消费它，ship-dark，prod 有句级数据后自动点亮。

## 目标

在阅读器右侧「跨藏对照」面板（`ReaderParallelPanel`）新增第三个 tab「按句对读」，把 `sentence_alignments` 的句级对齐以**堆叠句对卡片 + 点击锁定**呈现，让用户逐句对照汉文与巴/藏原文。

## 非目标（YAGNI）

- 不做整卷正文 char-offset 叠加（否决的方案 B——复杂，主正文已在左侧主阅读区）。
- 不做侧栏→主阅读区的 char-offset 联动滚动（复杂、需真实数据调试；留作后续增强）。
- 不动现有「按经对读」「按段对读」两个 tab 的行为。
- 不新增后端（契约已由 P4-C 提供）。

## 后端契约（既有，冻结）

`GET /alignment/sentences/{text_id}/{juan_num}?limit=200` → `SentenceAlignmentResponse`：
```
{ text_id, juan_num, total,
  pairs: [ { side_a: {char_start, char_end, lang, text},
             side_b: {text_id, juan_num, char_start, char_end, lang, title, text},
             similarity, align_type ('1-1'|'1-2'|'2-1'), method, is_verified } ] }
```
- flag `enable_sentence_parallels=false` 或空表 → `{total:0, pairs:[]}`（永不报错）。
- `side_a` 恒为请求的经（当前卷汉文侧），`side_b` 为对应外文侧（带自己的 text_id/juan 供未来深链）。

## 架构

复用现有面板 tab 框架，新增一个自包含视图组件，与 `CanonicalView`/`ChunkView` 平级。

### 组件
- **`frontend/src/components/parallel/SentenceParallelView.tsx`**（新，**独立文件**——现有 `CanonicalView`/`ChunkView` 是内联在 `ReaderParallelPanel.tsx` 里的，但本组件独立成文件以便单测隔离，也避免继续撑大已 440+ 行的面板文件；不重构现有内联视图，超范围）
  - Props：`{ textId: number, juanNum: number }`（对齐 `ChunkView` 签名）。
  - react-query 拉数据：`queryKey: ["sentence-parallels", textId, juanNum]`，`queryFn: () => getSentenceParallels(textId, juanNum)`，`enabled: textId>0`，`staleTime: 10min`，`retry: false`（与 `ChunkView` 一致）。
  - 渲染：`pairs` 按 `side_a.char_start` 顺序（后端已排），逐个渲染为**句对卡片**：
    - 卡片内：`side_a.text`（汉文，上）/ `side_b.text`（外文，下），之间轻分隔。
    - 角标：`align_type` badge（`1-2`/`2-1` 标一对多；`1-1` 不显）、外文 `lang` Tag、`side_b.title` 淡显、`similarity` 以淡色小字显示（如 `0.94`）、`is_verified` 时一个"已校"标记。
  - **点击锁定**：点卡片 → 该卡片 active（高亮边/底 + 两行强调），其余轻度 dim；再点取消。active 态 `scrollIntoView({block:'nearest'})` 保证可见。纯前端状态（`useState<number|null>` 存 active index）。
  - 状态：loading（`Spin`）、error（`Alert`，可 retry）、empty（`Empty`，文案"本卷暂无逐句对齐"）。

### 面板接线（`ReaderParallelPanel.tsx`）
- items 数组**条件性**加入第三项 `{ key:'sentence', label: t('reader.parallel.tab_sentence'), children: <SentenceParallelView .../> }`——仅当句级有数据时出现（"空数据自动隐藏"）。
  - 用一个轻量 `useQuery(["sentence-parallels", textId, juanNum])`（与 view 内共享同 key，react-query 自动 dedupe，不重复请求）读 `total`，`total>0` 才 push 该 tab item。
- 默认 tab 选择（`effectiveKey`）逻辑**不变**（canonical>chunk）；「按句对读」作为已有数据时可点击的第三 tab。（"有数据时设为默认"留作后续小调，避免打扰现有精心注释的默认逻辑。）

### 数据流
```
SentenceParallelView / ReaderParallelPanel
  → client.getSentenceParallels(textId, juanNum)     [新增]
  → GET /api/alignment/sentences/{textId}/{juanNum}  [P4-C 冻结契约]
  → sentence_alignments（方向无关，已由读模型归一）
```

### client.ts
新增 `getSentenceParallels(textId: number, juanNum: number): Promise<SentenceAlignmentResponse>` + 对应 TS 类型（`SentenceAlignmentResponse` / `SentencePair` / side 结构），与现有 `getJuanAlignment`/`getCanonicalParallels` 的方法与类型风格一致。

## 错误 / 边界处理
- 端点报错 → `Alert` + retry（`retry:false` 下用户手动重试）。
- `total:0`（flag 关 / 空表 / 该卷无 curated 对齐）→ tab 不出现；即便直达也是 `Empty`。**这是 ship-dark 自激活的机制**：prod 跑完 `refine_sentence_alignments.py` 后自然点亮，无需前端改动。
- `1-2`/`2-1`：后端每个 pair 已把多句合并进 `side_a.text`/`side_b.text`，前端一个卡片即一对，`align_type` badge 标示，无需前端再拆分。
- 覆盖范围：句级只在有 curated 对齐的经上有数据（见运行手册 M2）——空态文案不误导为"全站应有"。

## 测试（vitest，全 fixture，不依赖 prod）
`SentenceParallelView.test.tsx`（镜像现有 `components/parallel/*.test.tsx` 模式）：
1. 渲染句对：给定 fixture pairs，断言汉/外文文本、lang tag、align_type badge 出现。
2. 点击锁定：点卡片 → active 高亮类名出现、再点取消。
3. 空态：`total:0` → `Empty`，不崩。
4. `1-2`/`2-1`：badge 正确渲染。
5. error 态：queryFn reject → `Alert`。
+ 面板层：`total>0` 时「按句对读」tab 出现、`total:0` 时不出现（可并入或单独轻测）。
+ `client.getSentenceParallels` 的 mock 测试（URL/参数/返回类型），镜像现有 client 测试。

## i18n
新增 key（三语 locale 全加，`{{n}}` 插值）：`reader.parallel.tab_sentence`、`reader.parallel.sentence.empty`、`reader.parallel.sentence.verified`、`reader.parallel.sentence.similarity`（如显示）、align_type 相关标签。无硬编码中文（ratchet 必过）。

## 验证门（CI 对齐）
`npx tsc -b --noEmit`、`npm run lint`、`npm run i18n:check`、`npm test`（含新测试）、`npm run build` 全过。

## 后续增强（不在本次）
- 侧栏卡片 ↔ 主阅读区的 char-offset 联动高亮/滚动（需真实数据调试）。
- 宽屏两列模式（当前堆叠卡片为窄栏/移动端优先）。
- 有句级数据时将「按句对读」设为默认 tab。
