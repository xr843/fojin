# /chat 长答案体验两条修复 — 设计

日期：2026-07-30
状态：待评审
影响范围：`frontend/src/pages/ChatPage.tsx`、`frontend/src/api/client.ts`、`frontend/src/styles/global.css`、`frontend/public/locales/{zh,zh-Hant,en}/translation.json`、`backend/app/services/chat.py`

上一轮（PR #1068，`b2812583`）解决了首屏留白。这一轮解决**长答案**的两个行为缺陷 —— 与 ChatGPT 对比后按「影响 × 改动成本」排在最前的两条。

## P0 · 流式生成时抢用户的滚动条

### 问题

`onToken` 里无条件调 `scrollToBottom()`（`ChatPage.tsx:871`），而它就是 `bottomRef.current?.scrollIntoView`（`:710-712`）。**没有任何「用户是否在底部」的判断**，仓里目前零个 scroll 监听（实测 `grep -c onScroll` = 0）。

后果：长答案生成过程中用户上滚重读前半段，每来一个 token 就被拽回底部。fojin 的答案恰恰长（带多级标题与嵌套列表的结构化文档），滚动是刚需。ChatGPT 的做法是一旦用户上滚就停止自动跟随，并显示「回到底部」悬浮按钮。

### 做法

1. 消息滚动容器挂 `onScroll`，维护 `atBottomRef.current`，判据 `scrollHeight - scrollTop - clientHeight < 80`
2. `scrollToBottom(force = false)` —— 仅当 `force` 或 `atBottomRef.current` 为真时执行
3. 两处必须保持强制滚动：用户刚发出消息（`:852`，`force = true`）、点击「回到底部」按钮
4. `atBottom` 为假时在消息区右下角显示 `↓` 悬浮按钮；点击强制滚到底

### 为什么用 ref 而不是 state

`onToken` 的回调闭包在 `handleSendMessage` 内创建，**不随 state 更新重建** —— 读 state 会永远拿到闭包创建时的旧值，导致「永远认为用户在底部」或「永远认为不在」。这正是 `CLAUDE.md` 点名的 SSE 陷阱同一族（回调间只传原始值、不传会变的引用）。

判据本身提成模块级纯函数 `isNearBottom(el)`，以便单测。

### 边界

| 情形 | 行为 | 判断 |
|---|---|---|
| 加载历史会话（`:721` 滚到顶） | `atBottom` 转假，`↓` 出现 | 正确 |
| 空状态（无滚动内容） | `scrollHeight ≈ clientHeight` → `atBottom` 恒真，`↓` 不显示 | 正确 |
| 「加载更早消息」prepend 到顶部 | 会扰动 `scrollTop` 语义 | **现状问题**，现有代码本就没做滚动锚定，不在本次范围 |

## P1 · 检索证据发得太晚，等待期是白等

### 问题与既有设计的张力

后端事件时序（实测）：

```
chat.py:727   searching   静态文案「正在检索相关经文...」
chat.py:812   sources 由 _prepare_chat 产出（此后到发送前未被改写或过滤）
chat.py:939   token       答案第一个字
chat.py:1072  sources     召回列表 ← 所有 token 之后
```

检索早于生成完成，但召回结果要等答案全部生成完才发。等待期用户只看到一句静态文案，没有任何证据表明真的检索到了东西；前端 `onSearching` 还是空实现（`:908-910`）。

**但「晚发」是刻意的** —— `chat.py:1071` 上方注释：`# 回答完成后显示引用来源——先论点后论据，自然阅读顺序`。参考经文 chip 出现在答案下方是有道理的。

**而且提前发全量 sources 会打坏流式渲染**：`injectCitationLinks` 在 `sources` 为空时直接返回原文（`citationLinks.ts:34`），所以今天流式期间它空转。一旦提前拿到 sources，它会在**残缺文本**上开始改写 —— 第二遍扫描包裹裸露的 `《经名》`，而流式中的经名可能只写了一半（`《般若波`），会出现包裹后又随新 token 变化的闪烁与错包。

### 做法：新增独立的轻量事件，不动 sources 时机

**后端**：在生成开始之前、`sources` 已齐备之后，发一个新事件：

```python
{'type': 'retrieved', 'count': len(sources), 'titles': [去重后前 3 个 title_zh]}
```

`chat.py:1071-1072` 的 `sources` 发送**保持不动** —— 既守住「先论点后论据」，也避开 `injectCitationLinks` 的残缺文本风险。

**前端**：
1. `ChatMessageItem` 增加可选字段 `retrieval?: { count: number; titles: string[] } | null`
2. `StreamCallbacks` 增加 `onRetrieved?`；`client.ts` 的事件 switch 增加 `case "retrieved"`
3. `onRetrieved` 只写 assistant 消息的 `retrieval` 字段
4. thinking 渲染处（`:289-293`）有 `retrieval` 时改显示「已检索 N 部经典：《A》《B》《C》 · 正在生成回答…」，无则维持现状文案

### 承重约束：titles 绝不能写进 `content`

`THINKING_SENTINEL` 是**按身份比较**的哨兵，出现在 `:104`（定义）、`:231`、`:288`、`:930`、`:950`。一旦 `content` 被改写：

- `onDone` 里「流结束但从未收到 token → 转失败哨兵」的兜底失效（`:948-954`）
- 用户会永远卡在假的「正在检索…」上，且没有重试按钮

`:941-947` 的注释专门记录过这个失效模式。所以新数据必须走独立字段。

### 为什么只取前 3 部经名

召回通常 5–8 部，全列会把等待提示撑得比答案还长；3 部足以传达「真的在查藏经」。`count` 仍给全量数字，所以「已检索 8 部经典：《A》《B》《C》…」是诚实的。

## i18n

新增 2 键，`zh` / `zh-Hant` / `en` 三个文件同步添加：

| 键 | zh |
|---|---|
| `chat.retrieved_hint` | 已检索 {{n}} 部经典 |
| `chat.generating` | 正在生成回答 |

插值用 `{{n}}` **不是** `{{count}}`（`CLAUDE.md` 明确点名）。

上一轮那两个孤键（`chat.master_lens` / `chat.gallery_hint`）**不在本次范围** —— 用户已决定另开 `chore(i18n)` 处理。

## 测试

| 层 | 测什么 | 能否自动化 |
|---|---|---|
| P0 单测 | `isNearBottom(el)` 纯函数的判据（含边界 79/80/81） | 可 |
| P0 手工 | 上滚后不被拽回、`↓` 出现与点击 | 只能手工（jsdom 无真实滚动几何） |
| P1 后端 | 新事件在第一个 token **之前**发出；`sources` 仍是最后一个数据事件 | 可 |
| P1 前端 | `onRetrieved` 之后 `content` **仍等于** `THINKING_SENTINEL` | 可，且这是关键红测试 |
| P1 前端 | 有 `retrieval` 时渲染出经名与数量 | 可 |

P1 前端那条「content 仍是哨兵」是本次唯一能挡住承重约束被破坏的自动化测试 —— 若实现把 titles 写进 content，它必须红。落笔前先在未修改的代码上确认新测试会红。

## 风险

| 风险 | 处置 |
|---|---|
| `onToken` 读到闭包里的旧 `atBottom` | 用 ref 而非 state；判据提成纯函数单测 |
| titles 写进 content 导致「永久假检索中」 | 独立字段 + 关键红测试；`:941-947` 的注释已记录该失效模式 |
| 新事件被旧前端收到 | `client.ts` 的 switch 对未知 `type` 是 `default` 落空（无 throw），旧前端忽略即可，不需要版本协商 |
| 后端新 yield 位置错误导致 sources 被提前 | 后端测试同时断言「新事件在 token 前」与「sources 仍在最后」 |
