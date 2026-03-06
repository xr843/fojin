# 佛津 (FoJin) v3.2

全球佛教古籍数字资源聚合平台

聚合 421 个活跃数据源（覆盖 29 个国家/地区）、8,949 条目录记录、237,593 条辞典词条、28 语种。可通过典津联检扩展至 72.8 万条跨平台古籍资源。

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

- **多维检索**：经典检索（经名/译者/编号，覆盖 8,949 条经典目录）、全文检索（经文正文关键词）、联合检索（本地 + 典津 72.8 万条跨平台古籍）、辞典检索（6 部权威辞典、237,593 条词条，支持中/梵/巴利/英语种筛选），263 个数据源支持搜索跳转
- **经文阅读**：按卷浏览经文内容，支持多语种平行对读（汉/梵/巴利/藏/英），覆盖 28 语种
- **数据源导航**：421 个全球佛教数字资源（覆盖 29 个国家/地区），按国家/地区、语种、类型筛选，涵盖 CBETA、SuttaCentral、84000、GRETIL、BDRC 等主流佛学数据库
- **知识图谱**：9,600+ 实体、3,800+ 关系（人物、寺院、经典、宗派等），力导向图可视化探索
- **写本浏览**：通过 IIIF 协议查看 BDRC 等机构的数字化写本与善本影像

## 用户使用说明

### 搜索经典

1. 在首页或搜索页输入关键词（经名、译者、编号等），点击搜索
2. 默认进入「经典检索」Tab，可切换到「联合检索」（含典津平台）、「全文检索」（经文正文）或「辞典检索」（词条查询）
3. 左侧可按国家/地区、馆藏机构筛选外部数据源
4. 点击搜索结果的「在线阅读」进入阅读器，或「查看详情」进入经文详情页

### 阅读经文

1. 在经文详情页点击「在线阅读」进入阅读器
2. 左侧选择卷次，主区域显示经文内容
3. 底部可翻到上/下卷
4. 如需多语种对照，进入「平行对读」页面选择对照文本

### 辞典检索

1. 搜索页切换到「辞典检索」Tab
2. 输入词头（支持中文、梵文、巴利文）
3. 右上角下拉框可按语种筛选
4. 释义过长时点击「展开全文」查看完整内容

### 浏览数据源

1. 导航栏点击「数据源」进入数据源导航页
2. 通过国家/地区、语种、类型筛选感兴趣的数据源
3. 源卡片显示该数据源的能力标识（本地全文、搜索、IIIF、API）
4. 点击可跳转到对应数据源的官方网站

### 探索知识图谱

1. 导航栏点击「知识图谱」
2. 左侧搜索实体（人物、寺院、经典等），点击结果加载图谱
3. 中央图谱可拖拽、缩放，节点按类型着色
4. 调整深度滑块控制关系展开层数
5. 右侧面板显示选中实体的详细信息


## 典津跨平台联检

佛津对接了典津平台 (guji.cckb.cn) API，实现跨平台古籍资源发现：

- **数据源浏览**（`/dianjin`）：按国家/地区分组浏览典津 180 个数据源、72.8 万条古籍记录
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
| `GET /api/dictionary/search` | 辞典词条搜索（支持 q/lang/page/size 参数） |

## 数据导入管道

支持以下数据源的自动化导入：

| 脚本 | 数据源 | 语种 |
|------|--------|------|
| `import_catalog.py` | CBETA 经目 | lzh |
| `import_content.py` | CBETA 全文 | lzh |
| `import_84000.py` | 84000 藏传佛典 | bo, en, sa |
| `import_suttacentral.py` | SuttaCentral | lzh, pi, en |
| `import_gretil.py` | GRETIL 梵文文献 | sa |
| `import_dsbc.py` | DSBC 数字梵文佛典 | sa |
| `import_sat.py` | SAT 大正藏 | lzh, ja |
| `import_ddb.py` | DDB 电子佛学辞典 | lzh, en |
| `import_gandhari.py` | 犍陀罗语佛典 | pgd |
| `import_vri_tipitaka.py` | VRI 巴利三藏 | pi |
| `import_korean_tripitaka.py` | 高丽大藏经 | lzh, ko |
| `import_polyglotta.py` | 多语种佛典 | lzh, sa, bo, pi, en |
| `import_kanripo_catalog.py` | Kanripo 漢籍リポジトリ | lzh |
| `import_bdrc_manifests.py` | BDRC IIIF 写本 | bo |
| `import_dila_authority.py` | DILA 权威数据库 | lzh |
| `import_cbeta_alt_translations.py` | CBETA 异译关系 | lzh |
| `import_sc_glossary.py` | SuttaCentral 巴利语词汇表 | pi |
| `import_ncped.py` | NCPED 简明巴英辞典 | pi |
| `import_nti_dict.py` | NTI 佛学辞典 | zh |
| `import_edgerton_bhs.py` | Edgerton 佛教混合梵语辞典 | sa |
| `import_monier_williams.py` | Monier-Williams 梵英大辞典 | sa |

批量导入：

```bash
cd backend
python scripts/import_all.py
```

## 技术栈

- **前端**：React 18 + TypeScript + Vite + Ant Design 5 + Zustand + TanStack Query
- **后端**：FastAPI + SQLAlchemy (async) + Pydantic v2
- **数据库**：PostgreSQL 15 + pgvector（向量检索）+ pg_trgm（模糊搜索）
- **搜索**：Elasticsearch 8（ICU 分词）
- **缓存**：Redis 7
- **跨平台联检**：典津 API (guji.cckb.cn) + httpx AsyncClient
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

### 测试服务器部署

如需部署到内网测试服务器，可直接从本地同步代码和数据：

```bash
# 1. 同步代码
rsync -az --exclude node_modules --exclude dist ./ user@server:~/projects/fojin/

# 2. 启动服务
ssh user@server "cd ~/projects/fojin && docker compose up -d --build"

# 3. 运行迁移
ssh user@server "docker exec fojin-backend alembic upgrade head"

# 4. 从本地复制数据库（可选，比重新导入更快）
docker exec fojin-postgres pg_dump -U fojin -d fojin --format=custom --exclude-table=text_embeddings -f /tmp/fojin.dump
docker cp fojin-postgres:/tmp/fojin.dump /tmp/fojin.dump
scp /tmp/fojin.dump user@server:/tmp/
ssh user@server "docker cp /tmp/fojin.dump fojin-postgres:/tmp/ && docker exec fojin-postgres pg_restore -U fojin -d fojin --clean --if-exists --no-owner /tmp/fojin.dump"
```

## 项目结构

```
fojin/
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI 路由（search, texts, dictionary, chat 等）
│   │   ├── core/          # 核心模块（ES、异常体系、速率限制、XML 解析）
│   │   ├── models/        # SQLAlchemy ORM 模型
│   │   ├── schemas/       # Pydantic 请求/响应模型
│   │   └── services/      # 业务逻辑（搜索、典津客户端等）
│   ├── alembic/versions/  # 数据库迁移（0001–0057）
│   ├── scripts/           # 数据导入脚本
│   └── tests/             # pytest 测试（异常、模式、搜索 API）
├── frontend/
│   ├── src/
│   │   ├── components/    # 通用组件 + search/ 子目录（5 个搜索卡片组件）
│   │   ├── pages/         # 页面组件
│   │   ├── config/        # searchPatterns.json（150+ 搜索 URL 模板）
│   │   ├── utils/         # sourceUrls、工具函数
│   │   └── stores/        # Zustand 状态管理
│   └── nginx.conf         # Nginx 配置（gzip_static + 安全头）
├── elasticsearch/         # ES Dockerfile（ICU 插件）
└── docker-compose.yml     # 编排配置（含资源限制与端口绑定）
```

## 数据库迁移

迁移文件位于 `backend/alembic/versions/`，当前最新为 `0057`。

```bash
cd backend
# 升级到最新
alembic upgrade head
# 查看当前版本
alembic current
# 回退一步
alembic downgrade -1
```
