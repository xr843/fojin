# FoJin 佛津

### 问佛典，得到有据可查的答案

**以 AI 问答为核心的佛典平台：RAG 检索全球最大的开放佛典聚合（613 数据源、30+ 语种、三藏跨语检索），每个答案都链回它引用的原经段落。**

用自然语言提问，FoJin 的「小津」直接从藏经里答你 —— 检索增强生成（RAG）覆盖 68 万+ 段经文向量，关键词重排 + 本经召回，**可点击的 `【《经名》第N卷】` 引文**一点即开对应原文，反幻觉校验，引文抽屉还能 **汉 / 巴利 / 藏文 并列对照跨藏经**。也可切换 **15 位历史法师人格** 提问，每位限定其宗派核心经典。

让这些答案可信的，是底下这套语料。FoJin 把 **613 个数据源** 聚合成一个可检索平台 —— 10,500+ 部经典、23,500+ 卷全文（汉、巴利、藏、梵四大传统），**全球首个 LLM 驱动的三藏对读 RAG 平台**（CBETA × SuttaCentral × 84000，段落级对应由 LLM 验证），11 万+ 实体的知识图谱地图，32 部辞典 748K 词条。每个功能的存在，都是为了让答案更有据可查 —— 也让你拿到答案后能继续深挖。

FoJin 的定位是 **开放、跨藏、可验证的佛学知识基础设施** —— 不只是一个供人阅读的网站，而是一套别的工具可以「调用」的语料。每一段经文都带一个稳定、可解析的跨藏 **URN**（`fojin:cbeta/T0001.1`），而 **[`fojin-mcp`](https://pypi.org/project/fojin-mcp/)** 服务器让 AI 助手（Claude、ChatGPT、任意 [MCP](https://modelcontextprotocol.io) 客户端）直接从 FoJin 已校验的引文作答。

[在线 Demo](https://fojin.app) · [API 文档](https://fojin.app/docs) · [English README](../README.md) · [Discussions](https://github.com/xr843/fojin/discussions) · [Discord](https://discord.gg/76SZeuJekq) · [报告 Bug](https://github.com/xr843/fojin/issues)

---

## FoJin 解决了什么问题？

佛教典籍散落在全球数百个数据库中 —— CBETA、SuttaCentral、BDRC、SAT、84000、GRETIL 等等。每家界面、语种、数据格式都不一样。当你心里有个**问题** —— "《心经》说的'色即是空'到底什么意思？"、"这段经文的巴利本和汉译本差在哪？" —— 你花在**找对那段经文**上的时间，往往比读懂它还多。

**FoJin 直接替你回答这个问题。** 用自然语言问，小津从 613 个源里检索出相关段落，给出你能逐条核对的可点击引文。FoJin 做的其他一切 —— 全文阅读、跨藏对齐、知识图谱、32 部辞典 —— 都是为了让答案更有据可查，也让你拿到答案后能继续深挖：

| 你需要做什么 | FoJin 怎么帮 |
|---|---|
| **提个问题，得到有出处的答案** | **AI 问答（小津）** —— RAG 覆盖 68 万+ 段经文、重排、本经召回、可点击 `【《经名》第N卷】` 引文、跨藏引文抽屉、反幻觉校验 |
| **相信这个答案** | **可验证答案** —— 确定性引文白名单 + 逐字引号降级 + 每条答案信任状态；temp=0 下约 98% 对外可信 |
| 研究一个多步的难题 | **研究助手**（`/research`）—— 跨语料 + 辞典 + 知识图谱规划检索，再走同一套闸门综合成带引文的答案 |
| 从 AI 助手里调用 FoJin | **MCP 服务器** —— [`uvx fojin-mcp`](https://pypi.org/project/fojin-mcp/)；6 个只读、URN 可寻址工具，供 Claude / ChatGPT 调用 |
| 用某位法师的口吻问 | **法师人格模式** —— 15 位历史法师，各自限定其宗派核心经典 RAG |
| 跨数据库找一部经 | **多维检索** 覆盖 613 数据源中的 10,500+ 部 |
| 在线阅读全文 | **8,900+ 部** 共 23,500+ 卷 CBETA 风格全文 |
| 对照不同语种译本 | **平行阅读** 30+ 语种侧边栏对照 |
| **跨藏经对读经文** | **三语跨藏对读** —— 3,000+ 条 LLM 验证段对，覆盖《妙法蓮華經》↔ Toh 113（**259 对**）、《小品般若波羅蜜經》↔ Toh 11 Aṣṭasāhasrikā（**127 对**）、维摩诘、心经、四阿含 ↔ 尼柯耶全集、法句等 11 个 pair 定义 |
| 查佛学术语 | **32 部辞典 748K 词条**（汉/梵/巴利/藏/英语种） |
| 探索人物关系 | **知识图谱** 110K+ 实体 / 28K+ 关系（含 22K+ 师承链） |
| 找相似经文 | **语义相似度** 由 680K+ 向量驱动（pgvector + HNSW） |
| 探索佛教地理 | **知识图谱地图** 地理实体、寺院位置、师承弧线（Deck.GL） |
| 跟踪源更新 | **动态信息流** 613 数据源实时更新 |
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
docker exec fojin-backend python -m scripts.archive.misc.generate_embeddings --source cbeta

# SuttaCentral 早期佛典
docker exec fojin-backend python scripts/archive/imports/import_suttacentral.py

# 全部导入脚本（一次性导入脚本在 archive/ 下）
ls backend/scripts/archive/imports/
```

每个 importer 直接从原始源（CBETA、SuttaCentral 等）下载 —— 本仓库不附带任何数据。

## 从你的 AI 工具里调用 FoJin（MCP）

FoJin 已校验的跨藏语料，可通过已发布的 **[`fojin-mcp`](https://pypi.org/project/fojin-mcp/)** 服务器，被 AI 助手（Claude Desktop、ChatGPT 或任意 [MCP](https://modelcontextprotocol.io) 客户端）直接调用 —— 助手从 FoJin 的引文作答，而不是凭空幻觉。

```bash
uvx fojin-mcp                 # 免安装直接运行
# 或：pip install fojin-mcp && fojin-mcp
```

它对外暴露 6 个**只读**工具（走公开 API），每个返回的经文都带稳定、可解析的跨藏 **URN**（`fojin:cbeta/T0001.1`）：

| 工具 | 作用 |
|---|---|
| `search_corpus` | 跨聚合藏经语义检索 |
| `read_passage` | 读取指定经典 / 卷 |
| `get_parallels` | 某段经文的跨藏平行（汉 ↔ 巴利 ↔ 藏） |
| `lookup_dictionary` | 32 部辞典术语查询 |
| `lookup_entity` | 知识图谱实体事实 |
| `resolve_urn` | 把 FoJin URN 解析到原典位置 |

Claude Desktop 配置和 ChatGPT 接入见 **[`mcp-server/README.md`](../mcp-server/README.md)**。该服务器是一个薄的只读客户端：**不含任何凭据、不打包任何语料**，只调用 FoJin 的公开端点 —— 默认目标 `https://fojin.app/api`，可用 `FOJIN_API_BASE_URL` 改指向自托管实例。

## 主要功能

### 多维检索

按经名、译者、目录编号或全文关键词跨佛教大藏经检索。基于 Elasticsearch + ICU 分词支持多语。

### 全文阅读

8,900+ 部佛典 / 23,500+ 卷全文在线阅读。CBETA 风格排版，智能识别偈颂/散文，自动重排段落，字号可调。

### 平行阅读（30 语种）

汉文、梵文、巴利、藏文、英文、日文、韩文、犍陀罗文及其他 21 种语言侧边栏对照。

### 三语跨藏经对读（三语对读）

**全球首个 LLM 驱动的佛典跨藏经对读系统**。CBETA（汉文）、SuttaCentral（巴利）、84000（藏文）原本各守一语孤岛，FoJin 通过 LLM 验证的段落级对齐打通。

**当前覆盖（3,000+ 段级对齐，11 个 pair 定义）**：

| 经典 / 语料 | 源 | 目标 | 对数 | 类型 |
|---|---|---|---:|---|
| **《妙法蓮華經》** (2026-06-08) | T0262 罗什 (汉) | Toh 113 (藏) | **259** | 汉 ↔ 藏 |
| **《小品般若波羅蜜經》** (2026-06-09) | T0227 罗什 (汉) | Toh 11 Aṣṭasāhasrikā (藏) | **127** | 汉 ↔ 藏 |
| 《維摩詰所說經》 | T0475 罗什 (汉) | Toh 176 (藏) | 20 | 汉 ↔ 藏 |
| 《般若波羅蜜多心經》 | T0252 法月广本 (汉) | Toh 21 (藏) | 6 | 汉 ↔ 藏 |
| 念处经 Mahāsatipaṭṭhāna | MN 10 (巴利) | T0026 中阿含 | 50 | 巴 ↔ 汉 |
| 转法轮经 Dhammacakkappavattana | SN 56.11 (巴利) | T0099 杂阿含 | 17 | 巴 ↔ 汉 |
| 《法句經》Dhammapada | T0210 (汉) | SC dhp 26 vaggas (巴利) | 49 | 汉 ↔ 巴 |
| **中阿含 ↔ Majjhima Nikāya 全集** | MN 全 152 部 (巴利) | T0026 (汉) | ~1,800 | 巴 ↔ 汉 |
| **长阿含 ↔ Dīgha Nikāya 全集** | DN 全 34 部 (巴利) | T0001 (汉) | ~700 | 巴 ↔ 汉 |
| **杂阿含 ↔ Saṃyutta Nikāya 56** | SN 56 部 (巴利) | T0099 (汉) | ~150 | 巴 ↔ 汉 |
| **增一阿含 ↔ Aṅguttara Nikāya 4** | AN 4 部 (巴利) | T0125 (汉) | ~400 | 巴 ↔ 汉 |

置信度分布：全部 ≥ 0.75。原 MVP 抽样精度 **100%**。大乘汉藏批次：法华 (2026-06-08) **$1.70 / 259 对**（接受率 8.6%）；八千颂般若 (2026-06-09) **$3.64 / 127 对**（接受率 3.4%，因般若经"色不异空"式排比体跨语 1:1 段对应天然稀薄）。

**两个使用入口**：

1. **AI 问答** — 当小津引用已对齐经典时，引文抽屉显示 `[ 汉文 ] [ 巴利 (5) ] [ 藏文 (3) ]` 标签页，点切换即可对照不同语种段落（藏文显示 Noto Tibetan 字体）
2. **阅读器** — 点工具栏 🌐 **「多语对读」** 内联侧栏，默认「按经对读」tab 展示 SuttaCentral 学术对应（Akanuma 级权威，四阿含↔尼柯耶 3293 条），每条附 Pāli 原文 + Sujato 英译预览 + 阅读全文链接。切换「按段对读」tab 查看 embedding+LLM 段级对齐（实验，有噪音）。可与 AI 解读面板**同时打开**，各自拖拽调宽

**对齐管道**（`backend/scripts/build_alignments.py`）：
- pgvector top-20 候选粗召回
- LLM 精验证（DeepSeek V3）返回 `{is_parallel, confidence, reason}`
- 置信度 ≥ 0.75 入 `alignment_pairs` 表，唯一索引保证幂等
- $50 成本上限守护（MVP 实际 ~$0.15）
- 多目标 resolver 支持目标分散在多行的情况（如 SC Dhammapada 26 vagga）

RAG 检索层自动在命中 alignment 时把 `parallel_chunks` 注入 LLM context，回答可自然引用"巴利本作…"或"藏译作…"，禁止虚构。

**做大对齐集 —— 飞轮**：在上面的批处理管道之外，一套*对齐飞轮*（`backend/app/services/alignment_flywheel.py`）从已验证的对齐对**向外扩展**去挖新候选 —— 相邻 chunk 往往也对齐，所以在盲搜最近邻会被同语言匹配淹没的地方，这套方法又快又准。候选进入**人工评审**队列，只有被接受后才提升为 ground-truth `alignment_pairs`（`method='flywheel-verified'`）。**绝不自动入库 —— 人工评审是精度闸门**，而每确认一组对齐，都让下一轮挖掘更好。

### 辞典查询

32 部权威辞典共 748,000+ 词条，覆盖汉/巴/梵/藏/英 6 语种 —— NTI Reader、DPD、Apte、Monier-Williams、Rangjung Yeshe、佛光、丁福保、Soothill 等。完整词典清单见英文 README 详情。

### 知识图谱

110,000+ 实体（寺院、人物、经典、宗派、概念）+ 28,000+ 关系 —— 含来自 DILA Authority Database 的 22,000+ 条师承链 —— 力导向图可视化，点节点探索连接。

### AI 问答 —— 小津

**这是 FoJin 的核心。** 自然语言提问，小津从藏经原文中作答，使用 RAG（检索增强生成）覆盖 68 万+ embedding 向量 + HNSW 索引快速语义检索。答案之所以站得住，是因为检索把向量相似度、关键词重排和**本经召回**（你问的那部经一定被拉进上下文）结合起来，而且每一句被引用的原文，在能变成可点击引文之前都会先与检索到的来源核对。功能包括：

- 多轮对话上下文感知
- 关键词 + 可选 API cross-encoder **重排**提升答案质量
- **可点击引用** `【《经名》第N卷】` 格式 —— 点击在侧栏抽屉打开原文上下文，**MVP 经典还显示跨藏经对读多语标签**（见上方三语对读章节）
- **GFM markdown 表格** —— 比较类回答（如"中观 vs 唯识"）正常渲染表格
- **递进式追问建议**（概念 → 相关经典 → 修行实践）
- **智能数据源推荐** —— 用户问数据库时自动从 613 个源里推荐相关
- **元问题处理** —— 识别"你是谁/你能做什么"自我介绍类问题，跳过 RAG
- **反伪造引用规则** —— 系统提示禁止把未在检索结果出现的经名包装成 `【…】`，防止断链
- **阅读器内嵌分屏** AI 解读面板，可拖拽分割条独立调宽，配置 localStorage 持久化
- **「问小津」按钮** 阅读器选中文字直接问
- **Tab 键** 输入框中循环建议问题
- BYOK（Bring Your Own Key）支持多个 LLM 厂商

### 可验证答案 —— 每一句都能点回原典

信任就是重点。每条答案在到你面前之前，都过三道**确定性**闸门：

- **引文白名单** —— `【《经名》第N卷】` 引文，若那个来源没被真正检索到，就剥掉或纠正；引文链接绝不会指向 FoJin 没读过的东西。
- **引号核验** —— 引号里的文字必须是检索到原文的**逐字**子串（繁简已折叠）；不是逐字的"引文"会被**降级**成普通叙述，而不是冒充经文。
- **信任状态** —— 每条答案标注 `verified` / `citation_corrected` / `quote_relaxed` / `no_sources`，让你看清它有多有据。

在评测集上 temp=0 实测：原始模型只有约 11% 是逐字可信的，但过完这三道闸门后，**对外服务的答案约 98% 可信** —— FoJin 要么把你带到真实原文，要么如实存疑，绝不伪造经文。该指标（`served_trustworthy_rate`）在 `backend/eval/faithfulness.py` 里作为回归门槛被持续跟踪。

### 研究助手（研究助手）

面对一次检索答不了的多步问题 —— *"空性在般若、中观、唯识三系里如何被处理，并给出带引文的跨藏平行段落？"* —— 研究助手把问题**拆解**成步骤，跨语料、辞典、知识图谱**检索**，再**综合**出有据可查的答案。综合环节走的是和聊天*完全相同*的引文闸门，所以 agent 可以自由规划，但**不能引用它没检索到的东西**。入口在 `/research`（需登录）；API 为 `POST /api/research/query`。

### 法师人格模式

选一位佛教法师，按其教学风格回答，限定其宗派核心经典 RAG。15 位历史法师可选：

| 法师 | 宗派 | 核心教法 |
|---|---|---|
| 龙树 | 印度·中观 | 八不中道、缘起性空、二谛中道、戏论寂灭 |
| 智顗 | 天台宗 | 一念三千、三谛圆融、五时八教、止观双修 |
| 慧能 | 禅宗 | 直指人心、见性成佛、无念无相无住 |
| 玄奘 | 法相唯识宗 | 八识、三性、五位百法、转识成智 |
| 法藏 | 华严宗 | 法界缘起、四法界、十玄门、六相圆融 |
| 鸠摩罗什 | 三论宗/中观 | 八不中道、缘起性空、不二法门 |
| 印光 | 净土宗 | 信愿行、持名念佛、敦伦尽分 |
| 蕅益 | 天台/净土跨宗派 | 教宗天台行归净土、六信、性相融会 |
| 虚云 | 禅宗五宗兼嗣 | 参话头、起疑情、老实修行 |
| 米拉日巴 | 藏传·噶举派 | 雪山闭关瑜伽士、那洛六法、以道歌说法 |
| 阿姜查 | 南传·泰国森林禅林派 | 正念、放下、朴素生活化教学 |
| 宗喀巴 | 藏传·格鲁派 | 菩提道次第、三主要道、应成中观 |
| 阿底峡 | 藏传·噶当派（印藏桥梁） | 菩提道灯论、三士道、七因果 |
| 觉音 | 南传·上座部论师 | 清净道论、戒定慧、七清净十六观智 |
| 马哈希 | 南传·缅甸内观传统 | 标记现象法、腹部起伏、四念处密集禅修 |

每位法师含 100-150 行 system prompt（含传承、核心教义、说话风格、教学方法、典故、术语表）。选定法师后，RAG 检索**限定到该法师核心经典**（如选智顗只检索《摩诃止观》《法华玄义》等），引用更精准。

由 [Master-skill](https://github.com/xr843/Master-skill) 开源框架支持。

### 知识图谱地图

50,000+ 地理实体在交互世界地图上可视化 —— 寺院、历史地点、人物、宗派。基于 Deck.GL + MapLibre。

- **实体类型**：寺院（绿）/ 地点（紫）/ 人物（红）/ 宗派（蓝）
- **师承弧线**：可切换显示 8,000+ 条师徒动画弧线
- **中文过滤**：快速过滤只显示中文命名实体
- **实体搜索**：按名查找，支持简繁转换（OpenCC）

### 动态信息流

实时跟踪 613 数据源更新 —— 新增经典、译本发布、写本扫描、schema 变更。含学术内容聚合和平台总览。

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
| + 602 个其他源 | | |

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | React 18, TypeScript, Vite, Ant Design 5, Zustand, TanStack Query, D3.js, Deck.GL + MapLibre（地图） |
| 后端 | FastAPI, SQLAlchemy (async), Pydantic v2, SSE 流式 |
| 数据库 | PostgreSQL 15 + pgvector (HNSW) + pg_trgm |
| 搜索 | Elasticsearch 8 (ICU 分词) |
| 缓存 | Redis 7 |
| AI | RAG（680K+ 向量，BGE-M3，HNSW）+ 14 法师人格 + 多 LLM 厂商（OpenAI/Anthropic/DeepSeek/DashScope/Gemini/+10 家）+ 确定性引文/引号闸门 |
| 集成 | MCP 服务器（[`fojin-mcp`](https://pypi.org/project/fojin-mcp/)，stdio）+ 公开 REST API（OpenAPI/Swagger 文档）+ 跨藏 URN 方案 |
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
- JWT 闲置 30 天过期（滑动续期，自登录起最长 90 天）；`POST /api/auth/logout-all` 可一次吊销全部 token。生产强 secret 必填

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

- [x] **三语跨藏经对读** —— 11 个 pair 定义，3,000+ 条 LLM 验证对齐（CBETA / SuttaCentral / 84000；含法华 ↔ Toh 113、八千颂般若 ↔ Toh 11 两部大乘汉藏批次、四阿含 ↔ 尼柯耶全集、原 MVP 5 经）
- [x] AI 问答多语引文抽屉（汉/巴/藏并列）
- [x] Reader 多语对读内联侧栏（按经/按段双 tab，SC 权威 + 自家 RAG 双来源）
- [x] AI 答案 GFM markdown 表格渲染
- [x] 反伪造引用规则强化
- [x] 服务端 SEO meta 注入（每部经典独立标题/描述）
- [x] **确定性答案可验证性** —— 引文白名单 + 逐字引号降级 + 每条答案信任状态；temp=0 下 `served_trustworthy_rate` 约 98%，作为评测回归门槛
- [x] **跨藏 URN 方案** —— 稳定、可解析的经文标识（`fojin:cbeta/T0001.1`），与 CBETA / SuttaCentral / 84000 / GRETIL / VRI 互通
- [x] **MCP 服务器 —— 已发布到 PyPI（[`fojin-mcp`](https://pypi.org/project/fojin-mcp/)）** —— 6 个只读、URN 可寻址工具，供 Claude Desktop / ChatGPT 调用
- [x] **Agentic 研究助手**（`/research`）—— 规划 → 检索（语料 + 辞典 + 知识图谱）→ 走同一套引文闸门的有据综合
- [x] **对齐飞轮** —— anchor-expansion 候选挖掘 + 人工评审后提升为 ground-truth 对齐

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
