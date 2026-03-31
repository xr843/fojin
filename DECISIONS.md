# 架构决策记录 (Architecture Decision Records)

> 记录 FoJin 项目中关键的技术选型和架构决策，及其背后的原因。

## ADR-001: 向量数据库选型 — pgvector

- **日期**: 2024-06
- **状态**: 已采用
- **上下文**: 需要存储 420K+ embedding 向量用于语义搜索和相似段落发现
- **决策**: 使用 PostgreSQL pgvector 扩展 + HNSW 索引（`pgvector/pgvector:pg15` Docker 镜像）
- **备选方案**: Milvus/Weaviate（独立运维成本高，单机场景无需专用向量库）；Pinecone（SaaS 依赖，数据主权不可控）
- **后果**: 向量与业务数据同库，简化运维和事务一致性；HNSW 索引在 420K 量级下性能足够；未来数据量级增长到千万级可能需要重新评估

## ADR-002: 全文搜索 — Elasticsearch 8

- **日期**: 2024-06
- **状态**: 已采用
- **上下文**: 需要跨 30 种语言（中/梵/巴/藏/英）的全文检索，含 CJK 分词、高亮、聚合、自动补全
- **决策**: Elasticsearch 8 + ICU tokenizer（自定义 Dockerfile 安装 ICU 插件），`cjk_content` 分析器处理中文
- **备选方案**: PostgreSQL FTS（中文分词支持弱，多语言难配置）；MeiliSearch（聚合能力不足，缺少 collapse/inner_hits 等高级特性）
- **后果**: 多语言搜索体验优秀，支持 phrase suggestion、collapse by text_id、cardinality 聚合等高级功能；额外 1.5GB 内存开销

## ADR-003: 流式传输 — SSE

- **日期**: 2024-06
- **状态**: 已采用
- **上下文**: AI 问答需要逐 token 流式输出，提升用户感知速度
- **决策**: Server-Sent Events（SSE），通过 `send_message_stream` 异步生成器逐行 yield `data: {...}\n\n`
- **备选方案**: WebSocket（双向通信对 AI 问答场景过重，且 SSE 天然兼容 HTTP/CDN/Nginx 反代）
- **后果**: 实现简洁，Cloudflare CDN 兼容（通过 2KB padding 冲刷缓冲区）；仅支持服务器到客户端单向推送，但 AI 问答场景足够

## ADR-004: 前端状态管理 — Zustand

- **日期**: 2024-06
- **状态**: 已采用
- **上下文**: 需要管理认证状态、Timeline 筛选等全局状态，同时使用 TanStack Query 管理服务端数据
- **决策**: Zustand（`stores/authStore.ts`、`stores/timelineStore.ts`），服务端数据交给 TanStack Query
- **备选方案**: Redux（boilerplate 过重）；Jotai（原子化模型对本项目规模无明显优势）
- **后果**: 全局状态逻辑极简，与 TanStack Query 分工明确；store 文件仅 2 个，维护成本低

## ADR-005: ORM 选型 — SQLAlchemy 2.0 async

- **日期**: 2024-06
- **状态**: 已采用
- **上下文**: FastAPI 全异步架构，需要异步 ORM 操作 PostgreSQL
- **决策**: SQLAlchemy 2.0 async（`sqlalchemy[asyncio]==2.0.36`）+ asyncpg 驱动 + Alembic 迁移
- **备选方案**: Tortoise ORM（生态较小，迁移工具不够成熟）；raw SQL（开发效率低，无自动迁移）
- **后果**: 生态成熟，async session 与 FastAPI 无缝集成；支持复杂查询（`func.left`、`func.count` 等聚合操作直接用 ORM 表达）

## ADR-006: 重排策略 — 关键词重排 + 可选 API 交叉编码器

- **日期**: 2024-09
- **状态**: 已采用
- **上下文**: pgvector 向量召回后需要重排提升相关性，但不想强制依赖外部 API
- **决策**: 默认使用零配置的关键词重排（70% 向量分 + 20% 字符重叠 + 10% 标题匹配）；配置 `RERANKER_API_URL` 后自动切换为 API 交叉编码器（40% 向量 + 60% cross-encoder），失败时回退关键词重排
- **备选方案**: 本地部署交叉编码器（内存占用大，1GB 后端容器装不下）；纯 API 重排（无 API key 时无法降级）
- **后果**: 零配置即可用，有 API 时质量更高，故障时自动降级；关键词重排对中文古籍的字符级匹配效果尚可

## ADR-007: Embedding 模型 — BGE-M3

- **日期**: 2024-06
- **状态**: 已采用
- **上下文**: 需要对中文古籍（文言文）、梵文、巴利文、藏文等多语言文本生成 embedding
- **决策**: BAAI/bge-m3 作为默认 embedding 模型（`EMBEDDING_MODEL=BAAI/bge-m3`），通过 OpenAI 兼容 API 调用
- **备选方案**: OpenAI text-embedding-3（中文古籍理解力不如 BGE-M3）；多模型方案（运维复杂，一致性难保证）
- **后果**: BGE-M3 对中文表现优异，多语言能力覆盖项目需求；依赖外部 API 服务（SiliconFlow 等）提供推理

## ADR-008: 部署架构 — Docker Compose 单机

- **日期**: 2024-06
- **状态**: 已采用
- **上下文**: 个人项目，需要简单可靠的部署方案，包含 PG、ES、Redis、后端、前端、Umami 共 6 个服务
- **决策**: Docker Compose 单机部署，Nginx 反代 + Cloudflare CDN，所有内部端口绑定 `127.0.0.1`
- **备选方案**: Kubernetes（运维复杂度远超单人项目需求）；裸机部署（环境一致性差，迁移困难）
- **后果**: 一条 `docker compose up -d` 即可启动全部服务；每个容器有 mem_limit/cpus 限制；水平扩展受限，但当前流量规模无此需求

## ADR-009: 缓存策略 — Redis 选择性缓存

- **日期**: 2024-06
- **状态**: 已采用
- **上下文**: 需要缓存热门问题、匿名用户限额等高频读写数据，但不需要全站缓存
- **决策**: Redis 7 用于选择性缓存：匿名用户每日问答限额（IP 维度，24h TTL）、热门问题列表（1h TTL）、统计数据缓存
- **备选方案**: 全面缓存（缓存失效策略复杂，数据一致性风险高）；无缓存（匿名限额无法用数据库高效实现）
- **后果**: 内存占用极小（256MB 限制），只缓存真正需要的数据；缓存 miss 直接查库，无雪崩风险

## ADR-010: 国际化方案 — i18next

- **日期**: 2024-09
- **状态**: 已采用
- **上下文**: UI 需要支持 9 种语言（简繁中文、英日韩泰越僧缅），需要语言检测和按需加载
- **决策**: i18next + react-i18next + i18next-browser-languagedetector + i18next-http-backend
- **备选方案**: react-intl（ICU MessageFormat 语法对翻译人员门槛较高）；具体原因待补充
- **后果**: 生态成熟，浏览器语言自动检测 + HTTP 按需加载翻译文件，减少首屏体积；插件体系灵活
