# FoJin 佛津

### 全球佛教古籍数字资源聚合平台

**503 个数据源 · 30 种语言 · 30 个国家 · 23,500+ 全文卷次 · 一站式检索**

聚合全球佛教数字资源 —— 503 数据源中的 10,500+ 部经典（巴利、汉传、藏传、梵文四大传统），共 23,500+ 卷全文。**全球首个 LLM 驱动的三藏对读 RAG 平台**（CBETA × SuttaCentral × 84000），段落级跨藏经对应由 LLM 验证；同时提供 CBETA 风格阅读、含 8 位法师人格的 AI 问答（RAG + 宗派限定检索 + 引用）、含 31K+ 实体和 28K+ 关系的知识图谱可视化（基于 Deck.GL 的 50K 地理实体地图）、32 部辞典 748K 词条（覆盖 6 语种）、时间线可视化、动态信息流、收藏夹、引用导出、批注、书签、多语对读阅读。

[在线 Demo](https://fojin.app) · [API 文档](https://fojin.app/docs) · [English README](../README.md) · [Discussions](https://github.com/xr843/fojin/discussions) · [Discord](https://discord.gg/76SZeuJekq) · [报告 Bug](https://github.com/xr843/fojin/issues)

---

## FoJin 解决了什么问题？

佛教典籍散落在全球数百个数据库中 —— CBETA、SuttaCentral、BDRC、SAT、84000、GRETIL 等等。每家界面、语种、数据格式都不一样。学者花在**找经文**上的时间比**读经文**还多。

**FoJin 把这一切聚合到一个平台**：

| 你需要做什么 | FoJin 怎么帮 |
|---|---|
| 跨数据库找一部经 | **多维检索** 覆盖 503 数据源中的 10,500+ 部 |
| 在线阅读全文 | **8,900+ 部** 共 23,500+ 卷 CBETA 风格全文 |
| 对照不同语种译本 | **平行阅读** 30 语种侧边栏对照 |
| **跨藏经对读经文** | **三语跨藏对读** —— 5 部 MVP 经典含 142 条 LLM 验证段对（心经、念处经、转法轮经、法句经、维摩诘经） |
| 查佛学术语 | **32 部辞典 748K 词条**（汉/梵/巴利/藏/英语种） |
| 探索人物关系 | **知识图谱** 31K+ 实体 / 28K+ 关系（含 23K 师承链） |
| 找相似经文 | **语义相似度** 由 678K+ 向量驱动（pgvector + HNSW） |
| 自然语言问经文 | **AI 问答（小津）** 含 RAG、reranking、可点击引用、多语对读抽屉、追问建议 |
| 学某位法师 | **法师人格模式** 8 位历史佛教大师，每位限定其宗派经典 RAG |
| 探索佛教地理 | **知识图谱地图** 50K+ 地理实体，寺院位置、师承弧线（Deck.GL） |
| 跟踪源更新 | **动态信息流** 503 数据源实时更新 |
| 可视化历史 | **时间线 + 仪表板** 朝代分布、翻译趋势、分类分析 |
| 个人组织 | **收藏夹、书签、批注** 个人学习用 |
| 学术引用 | **引用导出**（BibTeX、RIS、APA）|

## 快速开始

```bash
git clone https://github.com/xr843/fojin.git
cd fojin
cp .env.example .env        # 启动前编辑 POSTGRES_PASSWORD
docker compose up -d         # 数据库迁移自动执行
```

访问：**http://localhost:3000**（API 文档：http://localhost:8000/docs）

> 首次启动后，平台已含数据库 schema 和数据源元数据，但**没有经文内容**。从公共数据源导入：

```bash
# CBETA 经目导入
docker exec fojin-backend python scripts/import_catalog.py

# CBETA 全文（需 xml-p5 仓库）
docker exec fojin-backend python scripts/import_content.py --all --xml-dir /data/xml-p5

# 生成 embedding（支持增量）
docker exec fojin-backend python -m scripts.generate_embeddings --source cbeta

# SuttaCentral 早期佛典
docker exec fojin-backend python scripts/import_suttacentral.py

# 全部导入脚本
ls backend/scripts/import_*.py
```

每个 importer 直接从原始源（CBETA、SuttaCentral 等）下载 —— 本仓库不附带任何数据。

## 主要功能

### 多维检索

按经名、译者、目录编号或全文关键词跨佛教大藏经检索。基于 Elasticsearch + ICU 分词支持多语。

### 全文阅读

8,900+ 部佛典 / 23,500+ 卷全文在线阅读。CBETA 风格排版，智能识别偈颂/散文，自动重排段落，字号可调。

### 平行阅读（30 语种）

汉文、梵文、巴利、藏文、英文、日文、韩文、犍陀罗文及其他 21 种语言侧边栏对照。

### 三语跨藏经对读（三语对读）

**全球首个 LLM 驱动的佛典跨藏经对读系统**。CBETA（汉文）、SuttaCentral（巴利）、84000（藏文）原本各守一语孤岛，FoJin 通过 LLM 验证的段落级对齐打通。

**MVP 首批 5 部经典，142 条对齐**：

| 经典 | 源 | 目标 | 对数 | 类型 |
|---|---|---|---:|---|
| 《般若波羅蜜多心經》 | T0252 (汉，法月广本) | Toh 21 (藏译) | 6 | 汉↔藏 |
| 《維摩詰所說經》 | T0475 (汉，罗什译) | Toh 176 (藏译) | 20 | 汉↔藏 |
| 念处经 Mahāsatipaṭṭhāna | MN 10 (巴利) | T0026 中阿含 | 50 | 巴↔汉 |
| 转法轮经 Dhammacakkappavattana | SN 56.11 (巴利) | T0099 杂阿含 | 17 | 巴↔汉 |
| 《法句經》Dhammapada | T0210 (汉) | SC Dhammapada 26 vaggas (巴利) | 49 | 汉↔巴 |

人工抽样精度 **100%**（10/10 完美对齐）。

**两个使用入口**：

1. **AI 问答** — 当小津引用 MVP 经典时，引文抽屉显示 `[ 汉文 ] [ 巴利 (5) ] [ 藏文 (3) ]` 标签页，点切换即可对照不同语种段落（藏文显示 Noto Tibetan 字体）
2. **阅读器** — 点工具栏 🌐 **「他藏对读」** 内联侧栏，列出当前卷所有有跨藏经对应的段落。每条可展开看汉文 + N 条对应 + 置信度。可与 AI 解读面板**同时打开**，各自拖拽调宽，**不遮挡经文**

**对齐管道**（`backend/scripts/build_alignments.py`）：
- pgvector top-20 候选粗召回
- LLM 精验证（DeepSeek V3）返回 `{is_parallel, confidence, reason}`
- 置信度 ≥ 0.75 入 `alignment_pairs` 表，唯一索引保证幂等
- $50 成本上限守护（MVP 实际 ~$0.15）
- 多目标 resolver 支持目标分散在多行的情况（如 SC Dhammapada 26 vagga）

RAG 检索层自动在命中 alignment 时把 `parallel_chunks` 注入 LLM context，回答可自然引用"巴利本作…"或"藏译作…"，禁止虚构。

### 辞典查询

32 部权威辞典共 748,000+ 词条，覆盖汉/巴/梵/藏/英 6 语种 —— NTI Reader、DPD、Apte、Monier-Williams、Rangjung Yeshe、佛光、丁福保、Soothill 等。完整词典清单见英文 README 详情。

### 知识图谱

31,000+ 实体（人物、寺院、经典、宗派、概念）+ 28,000+ 关系 —— 含来自 DILA Authority Database 的 23,000 条师承链 —— 力导向图可视化，点节点探索连接。

### AI 问答 —— 小津

自然语言提问。小津基于 RAG（检索增强生成）回答，使用 678K+ embedding 向量 + HNSW 索引快速语义检索。功能包括：

- 多轮对话上下文感知
- 关键词 + 可选 API cross-encoder **重排**提升答案质量
- **可点击引用** `【《经名》第N卷】` 格式 —— 点击在侧栏抽屉打开原文上下文，**MVP 经典还显示跨藏经对读多语标签**（见上方三语对读章节）
- **GFM markdown 表格** —— 比较类回答（如"中观 vs 唯识"）正常渲染表格
- **递进式追问建议**（概念 → 相关经典 → 修行实践）
- **智能数据源推荐** —— 用户问数据库时自动从 503 个源里推荐相关
- **元问题处理** —— 识别"你是谁/你能做什么"自我介绍类问题，跳过 RAG
- **反伪造引用规则** —— 系统提示禁止把未在检索结果出现的经名包装成 `【…】`，防止断链
- **阅读器内嵌分屏** AI 解读面板，可拖拽分割条独立调宽，配置 localStorage 持久化
- **「问小津」按钮** 阅读器选中文字直接问
- **Tab 键** 输入框中循环建议问题
- BYOK（Bring Your Own Key）支持多个 LLM 厂商

### 法师人格模式

选一位佛教法师，按其教学风格回答，限定其宗派核心经典 RAG。8 位历史法师可选：

| 法师 | 宗派 | 核心教法 |
|---|---|---|
| 智顗 | 天台宗 | 一念三千、三谛圆融、五时八教、止观双修 |
| 慧能 | 禅宗 | 直指人心、见性成佛、无念无相无住 |
| 玄奘 | 法相唯识宗 | 八识、三性、五位百法、转识成智 |
| 法藏 | 华严宗 | 法界缘起、四法界、十玄门、六相圆融 |
| 鸠摩罗什 | 三论宗/中观 | 八不中道、缘起性空、不二法门 |
| 印光 | 净土宗 | 信愿行、持名念佛、敦伦尽分 |
| 蕅益 | 天台/净土跨宗派 | 教宗天台行归净土、六信、性相融会 |
| 虚云 | 禅宗五宗兼嗣 | 参话头、起疑情、老实修行 |

每位法师含 100-150 行 system prompt（含传承、核心教义、说话风格、教学方法、典故、术语表）。选定法师后，RAG 检索**限定到该法师核心经典**（如选智顗只检索《摩诃止观》《法华玄义》等），引用更精准。

由 [Master-skill](https://github.com/xr843/Master-skill) 开源框架支持。

### 知识图谱地图

50,000+ 地理实体在交互世界地图上可视化 —— 寺院、历史地点、人物、宗派。基于 Deck.GL + MapLibre。

- **实体类型**：寺院（绿）/ 地点（紫）/ 人物（红）/ 宗派（蓝）
- **师承弧线**：可切换显示 8,000+ 条师徒动画弧线
- **中文过滤**：快速过滤只显示中文命名实体
- **实体搜索**：按名查找，支持简繁转换（OpenCC）

### 动态信息流

实时跟踪 503 数据源更新 —— 新增经典、译本发布、写本扫描、schema 变更。含学术内容聚合和平台总览。

### 相似段落发现

阅读任意经文时，侧栏自动用 pgvector 余弦相似度找语义相似的其他经文段落 —— 跨经文呼应、相关注疏、主题关联。

### 时间线 + 统计仪表板

D3 交互图表可视化佛教文献史 —— 朝代分布、翻译趋势、语种结构、分类树形图、TOP 译者。学术 / 通俗模式可切换。

### 收藏夹、书签、批注

收藏经典到个人 collection，书签段落，添加批注供学习研究。

### 引用导出

BibTeX、RIS、APA 三种格式导出，方便学术论文与文献管理。

### 多语界面

9 种界面语言：简体中文、繁体中文、英文、日文、韩文、泰文、越南文、僧伽罗文、缅甸文。

## 数据源

FoJin 聚合全球主要佛教数字项目的数据。按研究领域分类（汉传、上座部、藏传、梵文、敦煌、艺术、辞典、数字人文），可按地区、语种、类型筛选：

| 源 | 内容 | 语种 |
|---|---|---|
| [CBETA](https://cbeta.org) | 汉文佛典电子大藏 | 文言 |
| [SuttaCentral](https://suttacentral.net) | 早期佛典 | 巴利、汉、英 |
| [84000](https://84000.co) | 藏传佛典英译 | 藏、英、梵 |
| [BDRC](https://bdrc.io) | 藏文写本（IIIF） | 藏 |
| [SAT](https://21dzk.l.u-tokyo.ac.jp/SAT/) | 大正藏 | 汉、日 |
| [DILA](https://authority.dila.edu.tw) | 权威数据库（人物、地点、目录） | 多语 |
| [GRETIL](http://gretil.sub.uni-goettingen.de) | 梵文电子文本 | 梵 |
| [VRI Tipitaka](https://tipitaka.org) | 巴利圣典 | 巴利 |
| [Korean Tripitaka](http://kb.sutra.re.kr) | 高丽藏 | 汉、韩 |
| + 492 个其他源 | | |

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | React 18, TypeScript, Vite, Ant Design 5, Zustand, TanStack Query, D3.js, Deck.GL + MapLibre（地图） |
| 后端 | FastAPI, SQLAlchemy (async), Pydantic v2, SSE 流式 |
| 数据库 | PostgreSQL 15 + pgvector (HNSW) + pg_trgm |
| 搜索 | Elasticsearch 8 (ICU 分词) |
| 缓存 | Redis 7 |
| AI | RAG（678K+ 向量，BGE-M3，HNSW）+ 8 法师人格 + 多 LLM 厂商（OpenAI/Anthropic/DeepSeek/DashScope/Gemini/+10 家） |
| 部署 | Docker Compose, Nginx (gzip, 安全头), Cloudflare CDN |
| CI | GitHub Actions（lint、test、安全扫描） |

## 开发

```bash
# 后端
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload

# 前端
cd frontend
npm install
npm run dev

# 测试
cd backend && pytest tests/ -q
```

## 安全

- 容器非 root 运行（backend `app` 用户、frontend `nginx` 用户）
- 多阶段 Docker 构建（生产镜像不含编译工具）
- 内部服务仅绑定 `127.0.0.1`
- 每个容器内存/CPU 上限
- CSP、X-Frame-Options、X-Content-Type-Options 头
- 所有搜索参数有长度限制
- JWT 8 小时过期，生产强 secret 必填

## 贡献

欢迎贡献！添加新数据源、改进搜索、修 bug、翻译界面 —— 都欢迎。

1. Fork 仓库
2. 创建 feature 分支（`git checkout -b feat/amazing-feature`）
3. 提交（`git commit -m 'Add amazing feature'`）
4. 推送（`git push origin feat/amazing-feature`）
5. 开 Pull Request

详见 [CONTRIBUTING.md](../CONTRIBUTING.md)。

## 路线图

详细的功能实现历史与未来规划见 [英文 README](../README.md#roadmap)。**最近完成**：

- [x] **三语跨藏经对读 MVP** —— 5 部经典 × 142 条 LLM 验证对齐（CBETA / SuttaCentral / 84000）
- [x] AI 问答多语引文抽屉（汉/巴/藏并列）
- [x] Reader 他藏对读内联侧栏（与 AI 面板共存）
- [x] AI 答案 GFM markdown 表格渲染
- [x] 反伪造引用规则强化
- [x] 服务端 SEO meta 注入（每部经典独立标题/描述）

**正在做**：
- [ ] 三语 MVP v1.1 —— 扩展到 20+ 经典（法华、华严、中论、楞伽、阿含全量 ↔ 尼柯耶）
- [ ] 主题本体浏览页
- [ ] 跨语种检索（汉文查询找梵/巴/藏结果）

## 许可证

[Apache License 2.0](../LICENSE) —— 仅适用于 FoJin 源代码。第三方数据源各自保留许可（CC BY-NC-SA、CC0、CC BY-NC-ND 等）。详见 [NOTICE](../NOTICE)。

## 致谢

FoJin 建立在全球佛教数字人文社区的慷慨工作之上。特别感谢：

- [CBETA](https://cbeta.org) 中華電子佛典協會
- [SuttaCentral](https://suttacentral.net) 早期佛典
- [BDRC](https://bdrc.io) 佛教数字资源中心
- [84000](https://84000.co) 藏传佛典翻译
- [SAT](https://21dzk.l.u-tokyo.ac.jp/SAT/) 大藏经数据库
- 其余数据源详见 [Sources 页面](https://fojin.app/sources)

## 相关项目

- [Master-skill](https://github.com/xr843/Master-skill) —— 佛教法师 AI 人格框架（FoJin 法师模式底层）
- [The Open Buddhist University](https://buddhistuniversity.net) —— 免费佛学课程、书籍、百科

## 联系

[Discussions](https://github.com/xr843/fojin/discussions) · [Issues](https://github.com/xr843/fojin/issues) · [contact@fojin.app](mailto:contact@fojin.app)
