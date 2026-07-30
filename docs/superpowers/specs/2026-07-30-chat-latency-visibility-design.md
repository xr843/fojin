# /chat 响应速度：先看清，再让等待有内容 — 设计

日期：2026-07-30
状态：待评审
影响范围：`backend/app/services/rag_retrieval.py`、`backend/app/services/chat.py`、`frontend/src/api/client.ts`、`frontend/src/pages/ChatPage.tsx`、`frontend/src/styles/global.css`、`frontend/public/locales/{zh,zh-Hant,en}/translation.json`

## 问题

生产实测（两个样本，同为登录态、默认模型）：

| 阶段 | 样本 1 | 样本 2 |
|---|---|---|
| 检索（`searching` → `retrieved`） | 2622ms | 5435ms |
| LLM 首字（`retrieved` → 首个 token） | 6903ms | 12860ms |
| **提问 → 首字** | **9.5s** | **18.3s** |

方差极大，且 LLM 首字是主导项。

## 三个查实的约束

**一、默认模型是推理模型，且是当前唯一可用的。** `llm_client.py:104` 的 `_REASONING_MODEL_MARKERS` 含 `"deepseek-v4"`，注释写明「its reasoning isn't reflected in the name」；`llm_catalog.py:39` 的 `DEFAULT_MODEL_ID = "deepseek:v4-pro"`。目录里另外三个模型在生产 UI 上均标「需配置 Key」——**换非推理模型提速这条路，在配好其他模型商的 Key 之前不可行**。用户已表示可以配，故列为后续选项，不在本轮。

**二、推理增量被整个丢弃。** `chat.py:891-894` 只读 `delta.content`；DeepSeek 推理阶段发的是 `delta.reasoning_content`，那些块 `content` 为空 → `if content:` 判假 → 丢弃。全仓从未读过 `reasoning_content`（仅在 `llm_client.py:98/115` 的注释里被提及）。**那 7–13 秒里服务端一直在收数据，一条都没用。**

**三、分段计时早已写好，但在生产里是关着的。** 代码里有 8 个 TIMING 埋点：

| 位置 | 测什么 |
|---|---|
| `chat.py:493` | `_prepare_chat` 总耗时 |
| `rag_retrieval.py:918` | Embedding（httpx 网络调用） |
| `rag_retrieval.py:967` | pgvector search |
| `rag_retrieval.py:752/755` | API rerank / 关键词 rerank |
| `rag_retrieval.py:1049` | 词典查询 |
| `rag_retrieval.py:1054` | RAG 总计 |
| `chat.py:515` | LLM call |

**全部是 `logger.debug`**，而 `main.py:36` 把 `app.*` 设为 `INFO` —— 一条都不输出。

这一条直接否掉了我最初的提案。我原打算「把 embedding 网络调用与 prep 的 4 次数据库往返并行」，但那是在**没有数据的情况下猜靶子**：检索的 2.6–5.4s 里，embedding 可能只占 0.3s，大头在 678K chunk 的 pgvector 上——那样并行 embedding 几乎无用，真正该动的是召回参数或索引。

## D1 · 先把测量打开

8 个 TIMING 埋点由 `logger.debug` 提到 `logger.info`。

- **为何不加新埋点**：已有的覆盖面正好够用，加新的等于重复。
- **日志量**：fojin 的 chat 规模（月约 730 chat 用户）下每轮 8 行可忽略；`docker logs fojin-backend` 是本仓既有的首要排查入口（`CLAUDE.md` 明说）。
- **为何不做成开关**：一个默认关闭的开关等于没打开；一个默认开启的开关等于直接改级别但多一层配置。真嫌吵可以后续合并成一行，但那属于优化输出格式，不属于本轮要回答的问题。

**这是后续一切优化的前提**，也是本轮唯一能回答「时间到底花在哪」的东西。

## D2 · 推理流不再丢弃，用作「仍在推进」的实证

### 生成器契约必须区分两种块

消费端现状（`chat.py:944-966`、`:1027`）：

```python
received_first_token = False
async for content in ...:
    if not received_first_token: received_first_token = True
    full_answer += content
...
if not received_first_token and not full_answer:   # 空回复兜底
```

若推理增量走同一条通道，会 ① 把 `received_first_token` 置真 → **空回复兜底失效**；② 拼进 `full_answer` → **推理过程变成答案正文**。后者直接违反本产品的最高准则（答案不得有错误或虚假信息）——推理过程里充满会被自己推翻的中间结论。

因此 `_stream_llm_once` / `_stream_attempt` 改为 yield 二元组 `(kind, text)`，`kind ∈ {"content", "reasoning"}`：

- `"content"` 的处理**与今天逐字相同**（置 `received_first_token`、累加 `full_answer`、发 `token` 事件）
- `"reasoning"` **只**用于发新事件，绝不触碰 `full_answer` 与 `received_first_token`
- Anthropic 分支（`chat.py:867-868`，仅 BYOK 自定义 URL 会走到）同步改为 yield `("content", text)`，不处理 `thinking_delta`——目录里没有 Anthropic 模型，超出本轮范围，但契约要一致

### `_stream_attempt` 的 `yielded` 只由 content 置位

重试语义是「已经吐过 token 就不重试，否则会重复输出」。推理是短暂的进度信号、重复无害，而答案重复有害。**`yielded` 只在 `kind == "content"` 时置真**——这恰好**保持今天的重试行为不变**（今天推理被丢弃，`yielded` 本来就不会因它置真）。

### 显示什么：进度，不是推理原文

后端按**节流**发 `reasoning` 事件（至多约 1 次/秒），载荷是累计字符数：

```json
{"type": "reasoning", "chars": 1820}
```

前端在已有的等待占位区把静态文案换成「正在推敲经文…（已思考 N 秒）」，N 由前端自己计时。

**为何不显示推理原文**：

1. 那是一行状态行，不是面板。滚动的中文尾巴每几十毫秒变一次，读不了，只是噪音。
2. 推理过程含大量会被推翻的中间结论。这个产品的准则是答案不得有错误或虚假信息，把它摆在答案位置上是拿准则冒险——哪怕样式不同，用户仍可能当成答案的一部分。
3. 我们真正需要它的地方是**证明系统还活着**：静态文案在 13 秒里读起来像卡死，而一个在动的计数器 + 持续到达的推理增量能证明「在推进」。字符数就够了。

**为何要节流**：推理可达 4000 token（`_with_reasoning_headroom` 给的额度），逐块转发等于把 SSE 流量放大数倍，而我们只显示一个数字。节流到 1 次/秒后总量约 10 条。

后续可选（不在本轮）：做成可展开面板，让愿意看的人读完整推理。那时才需要原文。

## D3 · 并行化 —— 本轮不做

等 D1 的生产数据出来再决定动哪里。若 embedding 占大头就并行它（但要保住 `_resolve_session` → 配额检查的错误顺序，见 `chat.py` 内注释「Resolve session first so ownership checks (403) come before config checks (503)」）；若 pgvector 占大头，那是召回参数或索引的问题，解法完全不同。

**不在没有数据时动检索管线** ——它直接决定模型看到哪些经文，是质量的上游。

## i18n

新增 2 键 × 3 locale：

| 键 | zh |
|---|---|
| `chat.reasoning_hint` | 正在推敲经文 |
| `chat.thinking_seconds` | 已思考 {{n}} 秒 |

插值用 `{{n}}` 不是 `{{count}}`。

## 测试

| 层 | 测什么 | 备注 |
|---|---|---|
| 后端 | `reasoning_content` 增量产出 `reasoning` 事件，且**不进** `full_answer` | 关键红测试 |
| 后端 | 只有 reasoning、无 content 时，仍走空回复兜底发 `error` | 守住 `received_first_token` 的语义 |
| 后端 | `reasoning` 事件被节流（模拟高频增量，断言事件数远小于增量数） | |
| 后端 | 现有 `test_chat_stream_*` 全绿（生成器契约改成二元组会波及它们） | 回归 |
| 前端 | 收到 `reasoning` 后占位区文案变化，且 `content` 仍是 `THINKING_SENTINEL` | 沿用上一轮的承重断言形式 |

生成器契约由 str 改为 tuple 会波及所有消费点与既有测试——这是本轮最可能打破既有行为的地方，全量后端测试必须跑。

## 风险

| 风险 | 处置 |
|---|---|
| 推理文本混入答案 | 二元组契约 + 关键红测试；`full_answer` 只接受 `kind=="content"` |
| 空回复兜底失效 | `received_first_token` 只由 content 置位 + 专门用例 |
| 重试语义被改变 | `yielded` 只由 content 置位，等价于今天的行为 |
| 契约变更打破既有测试 | 全量后端 pytest；`test_chat_stream_*` 六个文件重点看 |
| INFO 日志过吵 | 先观察；真吵再合并成一行，属输出格式优化 |
