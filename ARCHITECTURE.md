# FoJin（佛津）架构导航图

> 这是一份**面向阅读代码的人**的导航文档：帮你在 VSCode 里快速建立全局心智模型、找到每个功能对应的文件、并学会"一条链路怎么从前端走到数据库"。
>
> 它与现有文档分工如下，三者互补：
> - **本文（ARCHITECTURE.md）** — 模块地图 + 代码走读 + 名词表，回答"代码在哪、怎么连起来"。
> - [`README.md`](README.md) — 技术栈表、架构拓扑图、本地启动命令（第 286/299/326 行）。
> - [`DECISIONS.md`](DECISIONS.md) — ADR 架构决策记录，回答"**为什么**选 pgvector / ES / SSe"。
>
> 数据规模类数字（经文 9200+、向量 678K+、辞典 28.5 万+ 等）来自 `README.md` 与 `backend/app/main.py` 的项目自述，未在本文逐一核验；结构、文件、路由、链路均已对照当前代码（master 分支）。

---

## 1. 一分钟全景

FoJin 是一个**以 AI 问答为核心**的佛教数字文献平台：聚合 CBETA、SuttaCentral、84000、DILA 等 500+ 数据源的经文/译本/辞典，提供全文检索、平行对读、跨藏对照、知识图谱，以及最重要的——**基于经文的 RAG 问答**（`/chat`）。

技术上是一个 **FastAPI（异步）+ React 18 的单体仓库**，数据落在 PostgreSQL 15（pgvector 向量 + pg_trgm）、Elasticsearch 8（全文）、Redis 7（缓存）三套存储，全部用 Docker Compose 编排。

> 阅读优先级提示：本仓库 chat（问答）是产品重心。想最快理解全局，**先把第 6 节的 `/chat/stream` 链路走一遍**——它一次性串起 api → service → model → 三大存储，其余 30 个模块都是同一套分层套路的复制。

---

## 2. 仓库目录地图

```
fojin/
├── backend/                 # FastAPI 后端（Python，约 6.4 万行）
│   ├── app/
│   │   ├── main.py          # ★ 入口：FastAPI 实例、中间件、所有 router 装配、/api/health
│   │   ├── config.py        # ★ 全局配置（Pydantic Settings，读 .env）
│   │   ├── database.py      # ★ async engine / async_session（SQLAlchemy）
│   │   ├── api/             # 路由层（HTTP 端点，~30 个模块）
│   │   ├── services/        # 业务逻辑层（~25 个模块，重心在这）
│   │   ├── models/          # SQLAlchemy ORM 表模型（~17 个）
│   │   ├── schemas/         # Pydantic 请求/响应模型
│   │   ├── core/            # 基础设施：elasticsearch、rate_limit、auth、exceptions、xml_parser
│   │   └── data/            # 内置静态数据
│   ├── alembic/versions/    # 数据库迁移（156 个，schema 演进史）
│   ├── scripts/             # 数据导入/构建脚本（build_alignments、extract_structured_kg…）
│   ├── eval/                # 检索/问答质量评测
│   ├── tests/               # pytest 测试
│   └── requirements*.txt / pyproject.toml / Dockerfile
├── frontend/                # React 18 + TypeScript + Vite 前端
│   └── src/
│       ├── App.tsx          # ★ 路由表（react-router）
│       ├── pages/           # 页面组件（33 个，一页一功能）
│       ├── components/      # 复用组件（按域分：search/kg/kg-map/parallel/timeline/dashboard）
│       ├── api/             # 调后端的客户端（client.ts + 各域）
│       ├── stores/          # Zustand 全局状态（authStore…）
│       ├── styles/ config/ types/ utils/
├── docs/                    # README_zh、SEO_SETUP、mitra-alignment、works-audit、screenshots…
├── docker-compose.yml       # ★ 编排：postgres/es/redis/backend/frontend/umami
├── deploy.sh                # 生产部署脚本（VPS）
├── fojin-backup.sh          # 数据库备份
└── README / DECISIONS / CHANGELOG / SECURITY / CONTRIBUTING …
```

★ = 想理解全局必看的"枢纽文件"。

---

## 3. 后端分层架构

后端是经典的三层 + 基础设施层，**数据严格单向流动**：

```
HTTP 请求
   │
   ▼
app/api/*.py          路由层：解析参数、鉴权、调用 service、返回 schema
   │                  （薄层，不写业务逻辑）
   ▼
app/services/*.py     业务层：核心逻辑都在这（RAG、检索、对齐、KG、鉴权…）
   │
   ├──► app/models/*.py   ORM：SQLAlchemy 表模型 → PostgreSQL
   ├──► app/core/elasticsearch.py → Elasticsearch（全文检索）
   └──► app.state.redis            → Redis（缓存 / 限流 / 配额）
```

`backend/app/main.py` 是装配中心，值得先通读一遍，它定义了：
- **生命周期 `lifespan`**：启动时初始化 ES、构建 gaiji（缺字）规范化器、启动跨藏对照 catalog 预热后台循环；关闭时清理。
- **中间件链**：CORS → `RateLimitMiddleware`（限流）→ `RequestLoggingMiddleware`（每请求日志）→ `LastActiveMiddleware`（用户活跃时间，Redis 5 分钟节流）。
- **异常处理**：`FoJinError` 统一映射、422 校验错误详细日志（避免前端"请求失败"黑盒）。
- **全部 router 装配**（`app.include_router(..., prefix="/api")`），以及 SEO 系列在根路径（无 `/api` 前缀）。
- `/api/health`：检查 Redis / PostgreSQL / Elasticsearch 三件套连通性。

> 提示：日志级别在 main.py 顶部被显式拉到 INFO（仅 `app.*` 命名空间），所以 `docker logs fojin-backend` 能看到 chat 阶段标记、鉴权事件、模型回退等关键日志。这是定位线上问题的第一入口。

---

## 4. 后端模块速查表

### 4.1 路由层 `app/api/`（按域）

| 域 | 文件 | 说明 |
|---|---|---|
| **问答（产品核心）** | `chat.py` | `/chat`、`/chat/stream`（SSE）、附件、模型列表、法师、配额、热门问题、会话/消息历史 |
| 搜索 | `search.py` / `search_unified.py` | 全文/全文内容检索、建议、筛选（走 ES） |
| 经文 | `texts.py` | 经文元数据、卷（juan）内容读取 |
| 对齐/跨藏 | `alignment.py` | 跨藏对照面板、catalog（带预热缓存） |
| 知识图谱 | `knowledge_graph.py` / `relations.py` | 实体、关系、图遍历、平行对读 |
| 辞典 | `dictionary.py` | 六部辞典检索 |
| FRBR 作品 | `works.py` | 作品脊椎（只读） |
| 引用/导出 | `citations.py` / `exports.py` | BibTeX/RIS/Chicago 引用、PDF/EPUB 导出 |
| 用户体系 | `auth.py` / `bookmarks.py` / `history.py` / `annotations.py` / `notification.py` | 认证、书签、阅读历史、批注、通知 |
| 数据源 | `sources.py` / `source_suggestions.py` / `feed.py` | 数据源信息、社区推荐、动态流 |
| 统计/后台 | `stats.py` / `admin.py` / `feedback.py` | 仪表盘、时间线、管理后台、反馈 |
| 图像 | `iiif.py` | IIIF manifest |
| 标准引用 | `urn.py` | URN 稳定文本引用解析 |
| 分享/SEO | `share.py` / `og.py` / `sitemap.py` / `rss.py` / `seo.py` / `seo_persons.py` / `seo_dict.py` | 分享页、OG 卡片、站点地图、RSS、SSR 落地页 |
| 联邦检索 | `dianjin.py` | 典津跨平台古籍检索（可选模块，import 失败则跳过） |

### 4.2 业务层 `app/services/`（重心，按重要度）

| 文件 | 行数级 | 职责 |
|---|---|---|
| `chat.py` | ~1755 | ★ 问答总控：会话/消息 CRUD、`send_message` / `send_message_stream`（SSE）、配额、热门问题 |
| `master_profiles.py` | ~1390 | 14 位法师人格（三大传统） |
| `rag_retrieval.py` | ~807 | ★ RAG 检索：`retrieve_rag_context`（向量+全文召回，喂给 LLM） |
| `search.py` | ~829 | 检索逻辑（ES 查询构造、高亮、聚合、collapse） |
| `knowledge_graph.py` | ~797 | 知识图谱查询与图遍历 |
| `citation_guard.py` / `citation.py` / `quote_verifier.py` | — | 引用守卫与核验（防 LLM 引用幻觉） |
| `precise_retrieval.py` | — | 精确召回（本经/卷级定位） |
| `embedding.py` | — | 向量化（BGE-M3，对接 embedding API） |
| `llm_catalog.py` | — | 多 LLM 供应商目录（OpenAI/Anthropic/DeepSeek/DashScope/Gemini…） |
| `gaiji.py` / `goryeo.py` | — | CBETA 缺字规范化、高丽藏处理 |
| `source.py` / `source_health.py` | — | 数据源元数据与健康巡检 |
| 其余 | — | `auth` `bookmark` `annotation` `history` `feed_service` `stats_service` `admin_service` `usage_service` `relation` `text` `content` `provenance` `iiif` `aliyun_sms` `oauth` `ai_diff*` `attachment_parser` `urn` |

### 4.3 数据模型 `app/models/`（SQLAlchemy → PostgreSQL）

`text`（经文）、`chat`（会话/消息）、`user`、`knowledge_graph`、`relation`、`work`（FRBR）、`dictionary`、`source`、`annotation`、`feedback`、`feed`、`notification`、`iiif`、`gaiji`、`audit`、`hot_question`、`ai_diff_cache`。

> 注意：**表名 ≠ 模型类名**（例如模型类 `BuddhistSource` 对应表 `data_sources`）。写迁移前务必先 `\dt` 核对真实表名。

---

## 5. 数据与基础设施

| 存储 | 用途 | 关键点 |
|---|---|---|
| **PostgreSQL 15 + pgvector** | 业务数据 + 678K+ 向量（项目文档载） | HNSW 索引做语义检索；pg_trgm 做模糊匹配；向量与业务同库，事务一致 |
| **Elasticsearch 8** | 全文检索 | 自定义 ICU 分词器，`cjk_content` 分析器处理中文，支持 collapse/聚合/建议 |
| **Redis 7** | 缓存 / 限流 / 配额 | 跨藏 catalog 预热、匿名问答配额、用户活跃节流 |
| **LLM/Embedding API** | 问答生成 + 向量化 | 多供应商；默认走上游，可指向本地 vLLM/Ollama 离线部署 |

**数据库迁移**：`backend/alembic/versions/`（156 个）。部署前务必核对生产 `alembic_version` 与文件链，避免撞链。新增数据源走 alembic 迁移（不走后台 UI）。

---

## 6. 一条链路走读：`/chat/stream`（最值得先读）

这是产品核心路径。走完它，你就掌握了"一个请求如何穿过全部分层"。

```
① 前端 UI
   frontend/src/pages/ChatPage.tsx          用户输入问题、选法师/模型
        │  通过 SSE 接收流式回答
        ▼
② 前端 API 客户端
   frontend/src/api/client.ts               基础 fetch / 鉴权头
   frontend/src/api/chatModels.ts           模型列表
   frontend/src/api/chatAttachments.ts      附件上传
        │  POST /api/chat/stream
        ▼
③ 路由层
   backend/app/api/chat.py  @router.post("/stream")   (第 83 行)
        │  解析参数、鉴权、配额检查
        ▼
④ 业务层（核心）
   backend/app/services/chat.py
     send_message_stream(...)               (第 1254 行) 总控，SSE 逐 token 产出
        ├─► rag_retrieval.retrieve_rag_context()   (rag_retrieval.py:631) 向量+全文召回经文
        ├─► master_profiles                        套用法师人格 system prompt
        ├─► llm_catalog / embedding                选模型、调 LLM API
        └─► citation_guard / quote_verifier        核验引用，防幻觉
        ▼
⑤ 数据层
   models/chat.py（会话/消息落库）
   PostgreSQL(pgvector 向量召回) + Elasticsearch(全文召回) + Redis(配额/缓存)
        ▲
        └─ SSE 事件流回 ③ → ② → ① 实时渲染
```

> 调试这条链路的经验（来自历史事故，务必牢记）：
> - **SSE 流里 session 生命周期是反复踩坑点**：跨 session 只传 primitive（id），不要传 detached ORM 对象；写侧/读侧都出过"卡在『正在检索经文并生成回答』"。
> - **service 层截断 cap 与 schema cap 必须同步**，否则 reader 模式 422。
> - **SSE 静默失败必须 `logger.warning`**，否则前端只看到通用"请求失败"。

---

## 7. 前端结构

技术栈：React 18 + TypeScript + Vite + Ant Design 5 + Zustand（状态）+ TanStack Query（数据获取）+ D3.js / Deck.GL + MapLibre（图谱/地图可视化）。

**路由表在 `frontend/src/App.tsx`**，页面与路径一一对应（节选）：

| 路径 | 页面组件 | 功能 |
|---|---|---|
| `/` | `HomePage` | 首页 |
| `/search` | `SearchPage` | 全文检索 |
| `/chat` | `ChatPage` | ★ AI 问答（产品核心） |
| `/texts/:id` `/texts/:id/read` | `TextDetailPage` / `TextReaderPage` | 经文详情 / 阅读器 |
| `/cross-canon` | `CrossCanonPage` | 跨藏对照 |
| `/parallel/:textId` | `ParallelReaderPage` | 平行对读 |
| `/kg` `/map` `/person/:id` | `KnowledgeGraphPage` / `KGMapPage` / `PersonPage` | 知识图谱 / 地图 / 人物 |
| `/dictionary` | `DictionaryPage` | 辞典 |
| `/works/:slug` | `WorkDetailPage` | FRBR 作品 |
| `/timeline` `/dashboard` `/activity` | `TimelinePage` / `DashboardPage` / `ActivityFeedPage` | 时间线 / 仪表盘 / 动态 |
| `/admin/*` | `Admin*Page` | 管理后台（需 admin 角色，`ProtectedRoute` 守卫） |
| `/profile` | `ProfilePage` | 个人中心（需登录） |

**约定**：
- 页面在 `pages/`，复用组件按域放 `components/{search,kg,kg-map,parallel,timeline,dashboard}/`。
- 调后端统一走 `api/client.ts`；全局状态用 `stores/`（如 `authStore.ts`）。
- 危险页面用 `<RouteErrorBoundary>` 包裹（chat、kg、works 等）。
- i18n 已三语化推进中（搜索页等）；插值禁用 `{{count}}`，用 `{{n}}`。

---

## 8. 部署与运维

**编排**：`docker-compose.yml`，六个服务：

| 容器 | 镜像 | 内存上限 | 说明 |
|---|---|---|---|
| `fojin-postgres` | pgvector/pgvector:pg15 | 3g | 主库 + 向量 |
| `fojin-es` | elasticsearch:8（自定义 ICU） | 1536m | 全文检索 |
| `fojin-redis` | redis:7-alpine | 256m | 缓存/限流 |
| `fojin-backend` | 本地构建 | 1g | FastAPI（生产双副本滚动） |
| `fojin-frontend` | 本地构建（nginx） | 128m | 静态 + 反代 |
| `fojin-umami` | umami:postgresql | 256m | 行为统计（可选，opt-in） |

**部署走 `./deploy.sh`**（不要手动 `docker rm` + force-recreate，会竞态停服）。内部服务（PG/Redis/ES/backend/umami）只绑 `127.0.0.1`；nginx 负责 gzip、安全响应头、SSE 不压缩。前端容器对 docker host 网络可达，多用户环境需加认证反代。

**本地开发**（详见 README "Development"）：
```bash
# 后端
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt && alembic upgrade head
uvicorn app.main:app --reload
# 前端
cd frontend && npm install && npm run dev
# 测试
cd backend && pytest tests/ -q
```

API 文档：后端起来后访问 `/docs`（Swagger）或 `/redoc`。

---

## 9. 怎么在 VSCode 里继续探索

1. **打开仓库根目录**（而非单独 backend/frontend），跨前后端跳转才生效。
2. 装 **Python + Pylance**（后端跳定义/找引用/调用链）、ESLint（前端）。
3. 三键够用：`Ctrl+P` 跳文件、`Ctrl+T` 全工程符号、`F12`/`Shift+F12` 跳定义/找调用方。
4. 装 **GitLens**：本仓库每个 commit 都是规范 PR（`feat/fix(scope):`），用它逐 PR 读历史 = 读到每个功能的"为什么"。
5. 看不懂的代码段，直接问 Claude Code"这段做什么、谁调用、为什么这么写"——用 AI 反向讲解 AI 写的代码。
6. 配套速查见 `CLAUDE.md`（给 AI 会话的约定/命令速查）、`DECISIONS.md`（决策原因）。

---

## 10. 名词表

| 术语 | 含义 |
|---|---|
| **RAG** | 检索增强生成。先从经文库召回相关段落，再喂给 LLM 生成有依据的回答，是 `/chat` 的核心 |
| **BGE-M3** | 多语言文本向量模型，用于把经文/问题转成向量做语义检索 |
| **pgvector / HNSW** | PostgreSQL 向量扩展 / 近似最近邻索引，支撑语义检索 |
| **SSE** | Server-Sent Events，问答回答逐 token 流式推送的传输方式 |
| **CBETA** | 中华电子佛典协会，最大的中文佛典数据源（约 2.84 亿字入库） |
| **gaiji（缺字）** | CBETA 中无 Unicode 码位的生僻字，需规范化别名做检索匹配 |
| **对齐 / 跨藏对照** | 不同语言/藏经版本的经文逐段对应（汉↔藏↔梵↔巴），见 `alignment` 模块 |
| **FRBR Work（作品脊椎）** | 把同一部经的不同译本/版本归到一个抽象"作品"下，见 `works` 模块 |
| **KG（知识图谱）** | 人物、经文、宗派、概念之间的实体与关系网 |
| **法师模式（master）** | 14 位高僧大德的 AI 教学人格（三大传统），见 `master_profiles.py` |
| **典津（dianjin）** | 跨平台古籍联邦检索（可选模块），与商业"典津"无关 |
| **MITRA / Dharmamitra** | 外部佛典开源对齐/embedding 栈，可接入对齐与 RAG 主线 |
| **IIIF** | 国际图像互操作框架，用于经文写本图像交付 |
| **alembic** | 数据库迁移工具，`backend/alembic/versions/` 记录 schema 演进 |

---

*本文件由 Claude Code 基于当前 master 分支代码生成，作为人工阅读导航。代码演进后如与实际不符，以代码为准；欢迎直接修订本文。*
