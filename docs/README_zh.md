# 佛津 (FoJin) v3.3

全球佛教古籍数字资源聚合平台

聚合 504 个数据源（覆盖 30 个国家/地区）、9,200+ 条目录记录（巴利、汉传、藏传、梵文四大语系，其中 7,600+ 条含全文内容）、237,593 条辞典词条、30 语种。支持 8 种界面语言（中/英/日/韩/泰/越/僧伽罗/缅甸）。内置 AI 佛学助手「小津」（基于 RAG 语义检索），覆盖 7,290 部经文、34.7 万语义片段。

## 快速启动

### 使用 Docker Compose

```bash
cp .env.example .env
docker compose up -d
```

服务启动后（端口取决于 `.env` 配置）：
- 前端：http://localhost:3000
- 后端 API：http://localhost:8000/docs
- PostgreSQL：localhost:15432（默认 Docker 映射 5432）
- Elasticsearch：localhost:9200
- Redis：localhost:16379（默认 Docker 映射 6379）

### 本地开发（不使用 Docker）

**基础服务**：需要本地安装 PostgreSQL 15、Elasticsearch 8、Redis 7，或通过 Docker 仅启动基础服务：

```bash
docker compose up -d postgres elasticsearch redis
```

**后端**：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python scripts/init_es_index.py
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**数据导入**：

```bash
cd backend
# CBETA 经目导入
python scripts/import_catalog.py
# 多源导入编排器
python scripts/import_all.py
```

**前端**：

```bash
cd frontend
npm install
npm run dev
```

**测试**：

```bash
cd backend
pip install -r requirements-dev.txt
pytest tests/ -q
```

## 主要功能

- **多维检索**：经典检索（经名/译者/编号，覆盖 9,200+ 条经典目录）、全文检索（经文正文关键词）、辞典检索（6 部权威辞典、237,593 条词条，支持中/梵/巴利/英语种筛选），263 个数据源支持搜索跳转
- **经文阅读**：7,600+ 部经文支持在线全文阅读，支持多语种平行对读（汉/梵/巴利/藏/英），覆盖 30 语种
- **数据源导航**：504 个全球佛教数字资源（覆盖 30 个国家/地区），按国家/地区、语种、类型筛选，涵盖 CBETA、SuttaCentral、84000、GRETIL、BDRC 等主流佛学数据库
- **收藏与书签**：个人收藏夹、段落书签、批注功能，支持个性化学习管理
- **引用导出**：支持 BibTeX、RIS、APA 格式导出，方便学术引用
- **多语言界面**：支持中文、英文、日文、韩文、泰文、越南文、僧伽罗文、缅甸文 8 种界面语言
- **知识图谱**：9,600+ 实体、3,800+ 关系（人物、寺院、经典、宗派等），力导向图可视化探索
- **写本浏览**：通过 IIIF 协议查看 BDRC 等机构的数字化写本与善本影像
- **AI 佛学问答**：内置「小津」(XiaoJin) AI 助手，基于 pgvector RAG 语义检索，覆盖 7,290 部经文（34.7 万语义片段）。`/chat` 专页支持流式输出、引用跳转、对话导出，回答基于经文原文并附引用出处
- **经典专题**：按主题分类浏览佛教经典（般若、净土、华严、禅宗等），提供系统化的学习路径

## 技术栈

- **前端**：React 18 + TypeScript + Vite + Ant Design 5 + Zustand + TanStack Query
- **后端**：FastAPI + SQLAlchemy (async) + Pydantic v2
- **数据库**：PostgreSQL 15 + pgvector（向量检索）+ pg_trgm（模糊搜索）
- **搜索**：Elasticsearch 8（ICU 分词）
- **缓存**：Redis 7
- **AI 问答**：pgvector RAG 语义检索 + 多 LLM provider（OpenAI/DashScope/DeepSeek/SiliconFlow/Zhipu）
- **SEO**：react-helmet-async 动态 meta + JSON-LD 结构化数据 + sitemap.xml + 按路由静态 HTML 生成
- **部署**：Docker Compose + Nginx（gzip_static 预压缩 + 静态资源长缓存）
- **CI**：GitHub Actions

## 部署

### Docker Compose 部署（推荐）

```bash
cp .env.example .env
# 编辑 .env 填写 API 密钥等配置
docker compose up -d --build
# 运行数据库迁移
docker exec fojin-backend alembic upgrade head
```

所有容器已配置日志轮转（10MB × 3 文件），无需担心磁盘空间。

### 安全加固

v3.2 包含以下安全优化：

- **容器非 root 运行**：后端使用 `app` 用户，前端使用 `nginx` 用户
- **多阶段构建**：后端 Dockerfile 使用 builder 阶段，最终镜像不含编译工具
- **端口绑定**：PostgreSQL、Elasticsearch、Redis、Backend 端口仅绑定 `127.0.0.1`，不对外暴露
- **资源限制**：每个容器设置 `mem_limit` 和 `cpus` 上限，防止单容器耗尽资源
- **安全头**：Nginx 添加 CSP、X-Content-Type-Options、X-Frame-Options、Referrer-Policy
- **搜索参数限制**：所有搜索查询参数添加 `max_length=200`
- **JWT 过期时间**：从 24 小时缩短至 8 小时
- **速率限制修复**：正确读取 Nginx 反向代理 `X-Forwarded-For` 头，按真实 IP 限流

## 项目结构

```
fojin/
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI 路由（search, texts, dictionary, chat 等）
│   │   ├── core/          # 核心模块（ES、异常体系、速率限制、XML 解析）
│   │   ├── models/        # SQLAlchemy ORM 模型
│   │   ├── schemas/       # Pydantic 请求/响应模型
│   │   └── services/      # 业务逻辑（搜索等）
│   ├── alembic/versions/  # 数据库迁移（0001–0085）
│   ├── scripts/           # 数据导入脚本
│   └── tests/             # pytest 测试
├── frontend/
│   ├── src/
│   │   ├── components/    # 通用组件 + search/ 子目录
│   │   ├── pages/         # 页面组件
│   │   ├── config/        # searchPatterns.json（150+ 搜索 URL 模板）
│   │   ├── utils/         # 工具函数
│   │   └── stores/        # Zustand 状态管理
│   └── nginx.conf         # Nginx 配置
├── elasticsearch/         # ES Dockerfile（ICU 插件）
└── docker-compose.yml     # 编排配置
```

## 许可证

Apache License 2.0 — 详见 [LICENSE](../LICENSE)。

## 联系我们

邮箱：[contact@fojin.app](mailto:contact@fojin.app) &nbsp;&middot;&nbsp; [GitHub Discussions](https://github.com/xr843/fojin/discussions)
