# Observability（Prometheus 指标）

后端在应用根路径暴露 `GET /metrics`（Prometheus 文本格式）。实现在
`backend/app/core/metrics.py`，随 backend 默认启用（`METRICS_ENABLED=false`
可完全关闭）。

## 暴露模型（为什么它是安全的）

- `/metrics` 挂在**应用根路径**，不在 `/api` 下。
- `frontend/nginx.conf` 只代理白名单路径（`/api/`、`/docs`、SSR/SEO 路由等），
  **没有** catch-all `location /` 反代 —— 所以 `/metrics` 从公网不可达。
- 抓取方在 docker 网络内直接访问 `backend:8000/metrics` / `backend2:8000/metrics`。
- **不要**为它加 nginx location。若某天需要外部抓取，加认证反代，别裸开。

## 启动抓取栈（可选，生产机上执行）

```bash
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d
# Prometheus UI 只绑 127.0.0.1:9090，本地看板走 SSH 端口转发：
ssh -L 9090:127.0.0.1:9090 <host>   # 然后浏览器打开 http://localhost:9090
```

配置在 `observability/prometheus.yml`（30s 间隔、双副本打 `replica` 标签、
30 天保留、256m 内存上限 —— 这台机器有 cgroup OOM 前科，量力而行）。

## 指标清单

### HTTP（`MetricsMiddleware` 记录）

| 指标 | 类型 | 标签 | 说明 |
|---|---|---|---|
| `fojin_http_requests_total` | Counter | `method` `handler` `status` | 按路由模板计数（`/api/texts/{tid}`，不是原始路径——基数有界） |
| `fojin_http_request_duration_seconds` | Histogram | `method` `handler` | 整条中间件链的墙钟延迟 |

未匹配任何路由的请求（404 扫描噪音）**不记录**；`/metrics`、`/api/health`、
`/api/version` 被排除（健康探针每 10s 打一次，会淹没计数器）。

### Chat / RAG 管线

| 指标 | 类型 | 说明 |
|---|---|---|
| `fojin_rag_retrieval_seconds` | Histogram | `retrieve_rag_context` 全程（pgvector 召回 + rerank）。问答链路里除 LLM 外最大的耗时项 |
| `fojin_rag_context_chunks` | Histogram | 每次检索喂给 LLM 的 chunk 数。0 桶暴涨 = 检索空手而归，值得告警 |
| `fojin_citation_guard_mutations_total` | Counter（`kind`） | 反幻觉护栏改写次数。上升 = 模型在编造引用（检索或 prompt 回归）——学术工具最坏的失败模式 |
| `fojin_llm_estimated_tokens_total` | Counter（`provider` `model` `byok` `type`） | 估算 LLM token 数（prompt/completion）。chat 不抓真实 usage（流式需改 SSE 协议），按字符估算 × 单价——量级参考，非账单对账 |
| `fojin_llm_estimated_cost_usd_total` | Counter（`provider` `model` `byok`） | 估算 LLM 花费（美元）。**`byok="false"` 才是平台掏钱的部分**；`byok="true"` 是用户自带 key。价格表在 `app/services/llm_cost.py`，涨价时更新 |

> 成本护栏当前只做**可观测**，没有硬性封顶（真正的 per-user 日限额已由 `chat_quota` 的请求数配额兜底：匿名 10 / 登录 200）。要不要加"平台日预算超限即软降级"是产品决策——先在 Grafana 上按下面的 PromQL 观察 `byok="false"` 的花费趋势，需要再决定阈值。

### 常用 PromQL

```promql
# API p95 延迟（按 handler）
histogram_quantile(0.95, sum by (handler, le) (rate(fojin_http_request_duration_seconds_bucket[5m])))

# 5xx 比例
sum(rate(fojin_http_requests_total{status=~"5.."}[5m])) / sum(rate(fojin_http_requests_total[5m]))

# RAG 检索 p95
histogram_quantile(0.95, sum by (le) (rate(fojin_rag_retrieval_seconds_bucket[15m])))

# 检索空结果率（告警候选）
sum(rate(fojin_rag_context_chunks_bucket{le="0"}[1h])) / sum(rate(fojin_rag_context_chunks_count[1h]))

# 引用护栏改写速率（告警候选：> 0 持续即值得看）
sum by (kind) (rate(fojin_citation_guard_mutations_total[1h]))

# 平台掏钱的 LLM 花费速率（$/小时，排除 BYOK）—— 预算告警候选
sum(rate(fojin_llm_estimated_cost_usd_total{byok="false"}[1h])) * 3600

# 按模型看平台花费占比（哪个模型在烧钱）
sum by (model) (rate(fojin_llm_estimated_cost_usd_total{byok="false"}[6h]))
```

## 实现注记（改代码前先读）

- **没用 `prometheus-fastapi-instrumentator`**：它遍历 `app.routes` 并假设每个
  条目都有 `.path`，FastAPI 0.139 的内部 `_IncludedRouter` 节点没有——全测试套
  116 个用例因此炸 `AttributeError`。改为从 `request.scope["route"]` +
  `scope["path_params"]` 推导 handler 标签（见 `_handler_label` 及其单测）。
- **`handler` 标签必须保持有界**：任何改动如果可能让原始路径进标签
  （用户输入、无路由匹配的路径），就是在制造 Prometheus 基数爆炸。改
  `_handler_label` 前先跑 `tests/test_metrics.py`。
- 新增业务指标：在 `app/core/metrics.py` 定义（模块级单例，自动进默认
  registry / `/metrics` 输出），在调用点打点，测试模式照抄 `test_metrics.py`。

# 产品 KPI（Umami 事件）

Prometheus 量的是系统；下面这四个数量的是产品。定位（2026-08-27 拍板）：佛津是佛教文本的
「研读会话」——会话是笔记本、引文抽屉是阅读器、引文是可信度、注疏是深度、贴原文是入口。
评估任何 /chat 改动先问「它让一次研读会话更顺吗」，看这四个数，不看 PV。

数据在 Umami 的 Postgres 里（`docker exec -i fojin-postgres psql -U fojin -d umami`）。
⚠️ 该实例还托管另一个站，**每条查询都要 `website_id = 'c757a04c-82e0-4f53-a720-830b0e1a7287'`**。
⚠️ Umami v2 的 `session_id` 是「访客 × 月」指纹，不是一次访问；`distinct_id` 全空。

## /chat 事件目录

| 事件 | 何时打 | 备注 |
|---|---|---|
| `chat` | 用户主动提的新问题 | `question` 存前 30 字。**重试 / 重新生成 / 续写不打**（各记各的），否则分母虚高 |
| `chat_retry` | 失败气泡上点「重试」 | 可靠性信号，不是对答案不满 |
| `chat_regenerate` | 最后一条回答上点「重新生成」 | 对答案不满的信号；后端替换旧的那对 |
| `answer_truncated` | 收到 `truncated` 帧（finish_reason=length/max_tokens） | 上限 2000 tokens 不够用的证据 |
| `answer_continue` | 截断提示上点「继续写完」 | 续写请求带中断处结尾 80 字 |
| `chat_stream_error` | 流失败 | `stage`=no_token/mid_stream/empty_done，`reason`=后端 code；用户手动停止（cancelled）**不记** |
| `citation_click` | 点答案里的内联引文 | `text_id` |
| `source_click` | 点「参考经文」chip / 等待期 chip | `phase=retrieved` 是等答案时先读原文 |
| `chat_copy` | 复制回答 | 有用信号 |

## 四个 KPI

| KPI | 定义 | 口径备注 |
|---|---|---|
| **核对率** | 打过 `citation_click` 或 `source_click` 的访客 ÷ 打过 `chat` 的访客（也可按事件数：核对事件 ÷ 回答数） | 点过引文的人问得深 2.6×，这是产品核心承诺被用上的比例 |
| **隔天回访率** | 同一 `session_id` 在 ≥2 个不同日期打过 `chat` 的访客 ÷ 打过 `chat` 的访客 | `session_id` 按月重置，只能算月内；基线 12.5%（2026-08） |
| **重发率** | 同一访客 30 分钟内原样重发同一 `question`（中间没有 `chat_retry`/`chat_regenerate`）÷ `chat` | 基线 9%（222/2,4xx，2026-08）；有了「重新生成」后应降 |
| **截断率** | 客户端：`answer_truncated` ÷ (`chat` + `answer_continue` + `chat_regenerate`)。**服务端更准**：`docker logs fojin-backend` 里 `answer truncated` 行数 ÷ `phase-2 LLM done` 行数（后者每条回答都写 `finish_reason=`） | 2026-08-27 起才有数；一周后据此定 max_tokens 该不该从 2000 上调（R2b） |

服务端截断率一行命令（生产）：

```bash
docker logs fojin-backend --since 168h 2>&1 | grep -c "answer truncated"
docker logs fojin-backend --since 168h 2>&1 | grep -c "phase-2 LLM done"
# 按 reader 模式分开看：grep "answer truncated" | grep -c "reader=True"
```
