# 佛津 (FoJin) v3.0.0

全球佛教古籍数字资源聚合平台

聚合 329 活跃数据源、130+ 可搜索、8,900+ 目录记录、23 语种关联。同时，还可以通过典津联检扩展至 72.8 万条跨平台古籍资源。

## 快速启动

### 使用 Docker Compose

```bash
cp .env.example .env
docker compose up -d
```

服务启动后：
- 前端：http://localhost:3000
- 后端 API：http://localhost:8000/docs
- PostgreSQL：localhost:5432
- Elasticsearch：localhost:9200
- Redis：localhost:6379

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
# 配置环境变量（修改 .env 中的 host 为 localhost）
alembic upgrade head
python scripts/init_es_index.py
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

如需启用最新的"官方分发端 / 主导入端"数据层（`source_distributions`），请确保数据库已升级到最新迁移：

```bash
cd backend
alembic upgrade head
```

**数据导入**：

```bash
cd backend
# CBETA 经目导入
python scripts/import_cbeta.py
# 多源导入编排器（批量注册外部数据源）
alembic upgrade head  # 包含数据源 seed 迁移
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
pytest tests/test_smoke.py -q
```

## 主要功能

### 搜索与发现

- **全文检索**：基于 Elasticsearch 的全文搜索与元数据检索，支持朝代、部类、语种、数据源等多维度筛选
- **联合检索**：并发查询本地数据库 + 典津跨平台 72.8 万条古籍资源，结果合并展示
- **佛学辞典**：内置佛学术语词条查询

### 内容阅读

- **经文阅读器**：按卷浏览经文内容，自动记录阅读进度
- **平行对读**：多语种（汉文/梵文/巴利文/藏文/英文）文本对照阅读
- **写本浏览**：通过 IIIF 协议查看数字化写本与善本影像
- **引用生成**：支持 Chicago / APA / MLA / Harvard 四种引用格式

### 数据源管理

- **多源聚合**：329 个数据源（CBETA、SuttaCentral、84000、GRETIL、SAT、DDB、DILA 等），23 语种关联
- **分发端追踪**：区分数据源实体与官方分发端（Git 仓库、批量下载、API），标记主导入端
- **典津联检**：对接典津平台 180 个数据源，按 14 个国家/地区分组浏览

### 知识组织

- **知识图谱**：人物、寺院、经典、概念等实体及其关系的可视化探索
- **文本关联**：译本、异本等文本间关系管理与平行对读
- **跨源标识符**：同一文本在不同数据源中的标识符映射

### 学术协作

- **OCR 众包**：提交写本 OCR 识别任务，社区协作校对
- **文本标注**：对经文片段添加学术标注，支持提交→审核→发布流程
- **跨语对齐**：跨语种文本对齐任务与逐句校验
- **研究笔记**：Markdown 格式的研究笔记，可关联经文与卷次

### AI 问答

- **RAG 对话**：基于检索增强生成的佛学问答，AI 回答附带原文引用
- **会话管理**：持久化对话历史，支持多轮追问

### 开发者接口

- **REST API**：完整的 RESTful API，交互式文档 (`/docs`)
- **GraphQL**：支持复杂嵌套查询的 GraphQL 端点
- **公开 API v1**：面向第三方的 API Key 认证接口，支持作用域和速率限制
- **数据导出**：CSV、JSON、JSON-LD (Linked Data) 多格式导出
- **Webhook**：事件驱动的 Webhook 集成

### 用户系统

- **认证授权**：JWT 认证，角色权限控制（管理员/审核员/贡献者）
- **个人收藏**：经文书签与阅读历史
- **API Key 管理**：创建/撤销 API Key，查看用量统计

## 典津跨平台联检

佛津对接了典津平台 (guji.cckb.cn) API，实现跨平台古籍资源发现：

- **数据源浏览**（`/dianjin`）：按 14 个国家/地区分组浏览典津 180 个数据源、72.8 万条古籍记录
- **联合检索**（搜索页「联合检索」Tab）：并发查询本地 ES + 典津 API，合并展示结果
- **降级容错**：典津不可用时本地搜索不受影响，前端显示警告提示

### 配置

在 `.env` 中设置典津 API Key：

```bash
DIANJIN_API_KEY=sk-gcis-your-api-key-here
```

未配置时数据源浏览（公开 API）仍可使用，仅联合搜索不可用。

### 相关端点

| 端点 | 说明 |
|------|------|
| `GET /api/dianjin/health` | 典津 API 连通性检查 |
| `GET /api/dianjin/datasources` | 浏览典津数据源（公开，Redis 缓存 1h） |
| `GET /api/dianjin/region-labels` | 地区代码→中文名映射 |
| `GET /api/dianjin/institutions` | 机构列表（含地区信息） |
| `POST /api/dianjin/search` | 代理搜索到典津（需 API Key） |
| `GET /api/search/federated` | 联合检索（本地 + 典津并发） |

## 数据源分发端

平台现在区分：
- `data_sources`：面向用户的数据源实体（如 CBETA、SuttaCentral、84000）
- `source_distributions`：这些数据源对应的官方分发端（如 Git 仓库、批量下载、API）

新增接口：
- `GET /api/sources`：返回数据源及其嵌套的 `distributions`
- `GET /api/sources/{code}/distributions`：返回某个数据源的分发端列表
- `GET /api/sources/ingest/primary`：返回所有"主导入端"平铺清单，便于导入脚本和管理后台直接消费

当前已内置的高优先级主导入端包括：
- `CBETA XML P5`
- `SuttaCentral Bilara Data`
- `84000 Data TEI`

## 技术栈

- **前端**：React 18 + TypeScript + Vite + Ant Design 5 + Zustand + TanStack Query
- **后端**：FastAPI + SQLAlchemy (async) + Pydantic v2
- **数据库**：PostgreSQL 15
- **搜索**：Elasticsearch 8
- **缓存**：Redis 7
- **跨平台联检**：典津 API (guji.cckb.cn) + httpx AsyncClient
- **部署**：Docker Compose
- **API**：REST + GraphQL (Strawberry)，公开 API v1 (API Key 认证)
