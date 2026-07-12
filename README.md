<div align="center">

# FoJin 佛津

### Ask the Buddhist canon — get cited, verifiable answers.

**AI Q&A grounded in the world's largest open aggregation of Buddhist texts: 600+ sources, 30+ languages, trilingual cross-canon retrieval — every answer linked back to its source passage.**

Ask a question in plain language and FoJin's assistant **"XiaoJin"** answers from the canon itself — Retrieval-Augmented Generation over 680K+ embedded passages, optional cross-encoder reranking and root-sutra recall, **clickable 【《sutra》juan N】 citations** that open the exact source text, anti-hallucination guards, and a citation drawer with **side-by-side 汉 / 巴利 / 藏文 cross-canon parallels**. You can also ask in the voice of **15 historical Buddhist masters**, each scoped to their own tradition's scriptures.

What makes those answers trustworthy is the corpus underneath. FoJin aggregates **613 data sources** into one searchable platform — 10,500+ texts with 23,500+ volumes of full content in Classical Chinese, Pali, Tibetan and Sanskrit, **the first LLM-driven trilingual cross-canon parallel reading platform** (CBETA × SuttaCentral × 84000) with LLM-verified chunk-level alignment, a 110K+ entity knowledge graph on a Deck.GL geo map, and 32 dictionaries with 748K entries. Every feature exists to make the answers more grounded — and to let you go deeper once you have one.

FoJin is built to be **open, cross-canon, verifiable Buddhist knowledge infrastructure** — not just a site to read, but a corpus other tools can *call*. Every passage carries a stable, resolvable cross-canon **URN** (`fojin:cbeta/T0001.1`), and the **[`fojin-mcp`](https://pypi.org/project/fojin-mcp/)** server lets AI assistants (Claude, ChatGPT, any [MCP](https://modelcontextprotocol.io) client) answer from FoJin's cited passages directly.

[Live Demo](https://fojin.app) &nbsp;&middot;&nbsp; [API Docs](https://fojin.app/docs) &nbsp;&middot;&nbsp; [中文文档](./docs/README_zh.md) &nbsp;&middot;&nbsp; [Discussions](https://github.com/xr843/fojin/discussions) &nbsp;&middot;&nbsp; [Discord](https://discord.gg/76SZeuJekq) &nbsp;&middot;&nbsp; [Report Bug](https://github.com/xr843/fojin/issues)

[![CI](https://github.com/xr843/fojin/actions/workflows/ci.yml/badge.svg)](https://github.com/xr843/fojin/actions/workflows/ci.yml)
[![Security Scan](https://github.com/xr843/fojin/actions/workflows/security.yml/badge.svg)](https://github.com/xr843/fojin/actions/workflows/security.yml)
[![fojin-mcp on PyPI](https://img.shields.io/pypi/v/fojin-mcp?label=fojin-mcp&color=3775A9)](https://pypi.org/project/fojin-mcp/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/xr843/fojin?style=social)](https://github.com/xr843/fojin)

![FoJin — Global Buddhist Digital Text Platform](./docs/screenshots/hero.png)

</div>

---

## Why FoJin?

Buddhist texts are scattered across hundreds of databases worldwide — CBETA, SuttaCentral, BDRC, SAT, 84000, GRETIL, and many more. Each has its own interface, language, and data format. When you have a *question* — "what does the Heart Sutra mean by 'form is emptiness'?", "how do the Pali and Chinese versions of this passage differ?" — you spend more time hunting for the right passage than understanding it.

**FoJin answers the question for you.** Ask in plain language; XiaoJin retrieves the relevant passages from 613 sources and answers with clickable citations you can verify. Everything else FoJin does — full-text reading, cross-canon alignment, the knowledge graph, 32 dictionaries — exists to make those answers more grounded, and to let you go deeper once you have one:

| What you need | How FoJin helps |
|---|---|
| **Ask a question, get a sourced answer** | **AI Q&A ("XiaoJin")** — RAG over 680K+ passages, reranking, root-sutra recall, clickable 【《sutra》juan N】 citations, cross-canon citation drawer, anti-hallucination guards |
| **Trust the answer** | **Verifiable answers** — deterministic citation whitelist + verbatim-quote downgrade + per-answer trust state; ~98% served-trustworthy at temp 0 |
| Research a hard, multi-step question | **Research Assistant** (`/research`) — plans across corpus + dictionaries + knowledge graph, then synthesises a cited answer behind the same guards |
| Call FoJin from an AI assistant | **MCP server** — [`uvx fojin-mcp`](https://pypi.org/project/fojin-mcp/); 6 read-only, URN-addressable tools for Claude / ChatGPT |
| Ask in a master's voice | **Master Persona Mode** — 15 historical masters, each with tradition-scoped RAG |
| Find a sutra across databases | **Multi-dimensional search** across 10,500+ texts from 613 sources |
| Read the full text online | **8,900+ texts** with 23,500+ volumes of full content, CBETA-style layout |
| Compare translations | **Parallel reading** in 30+ languages side by side |
| Compare sutras across Buddhist canons | **Trilingual cross-canon parallel reading** — 3,000+ LLM-verified chunk alignments across Chinese / Pali / Tibetan covering Heart Sutra, Vimalakīrti, **Lotus Sutra (法华 ↔ Toh 113, 259 pairs)**, **8,000-verse Prajñāpāramitā (小品般若 ↔ Toh 11, 127 pairs)**, Satipaṭṭhāna + the full Āgama ↔ Nikāya corpus (MN/DN/SN/AN), Dhammapada |
| Look up Buddhist terms | **32 dictionaries**, 748K entries (Chinese/Sanskrit/Pali/Tibetan/English) |
| Explore relationships | **Knowledge graph** with 110K+ entities and 28K+ relations (22K+ lineage chains) |
| Discover similar texts | **Semantic similarity** powered by 680K+ embedding vectors (pgvector + HNSW) |
| Explore Buddhist geography | **Knowledge Graph Map** — geo-enabled entities, monastery locations, lineage arcs on Deck.GL |
| Track source updates | **Activity Feed** — real-time updates from 613 data sources |
| Explore history visually | **Timeline & Dashboard** — dynasty charts, translation trends, category analytics |
| Save and organize | **Collections, bookmarks, annotations** for personal study |
| Cite in research | **Citation export** (BibTeX, RIS, APA) for academic use |

## Quick Start

```bash
git clone https://github.com/xr843/fojin.git
cd fojin
cp .env.example .env        # edit POSTGRES_PASSWORD before starting
docker compose up -d         # database migrations run automatically
```

Then visit: **http://localhost:3000**

> API docs at http://localhost:8000/docs

After first startup, the platform has the database schema and source metadata but **no text content**. To import texts from public data sources:

```bash
# Import CBETA catalog (auto-scans local xml-p5 directory or fetches from remote)
docker exec fojin-backend python scripts/import_catalog.py

# Import CBETA full text content (requires xml-p5 repository)
docker exec fojin-backend python scripts/import_content.py --all --xml-dir /data/xml-p5

# Generate embeddings for AI Q&A (supports incremental processing)
docker exec fojin-backend python -m scripts.archive.misc.generate_embeddings --source cbeta

# Import SuttaCentral Early Buddhist Texts
docker exec fojin-backend python scripts/archive/imports/import_suttacentral.py

# See all available importers (one-off importers live under archive/)
ls backend/scripts/archive/imports/
```

Each importer downloads data directly from the original source (CBETA, SuttaCentral, etc.) — no data is bundled in this repository.

## Use FoJin from your AI tools (MCP)

FoJin's verified, cross-canon corpus is callable directly from AI assistants (Claude Desktop, ChatGPT, or any [MCP](https://modelcontextprotocol.io) client) via the published **[`fojin-mcp`](https://pypi.org/project/fojin-mcp/)** server — so the assistant answers Buddhist questions from FoJin's cited passages instead of hallucinating.

```bash
uvx fojin-mcp                 # zero-install run
# or: pip install fojin-mcp && fojin-mcp
```

It exposes six **read-only** tools over the public API, each returning passages with a stable, resolvable cross-canon **URN** (`fojin:cbeta/T0001.1`):

| Tool | What it does |
|---|---|
| `search_corpus` | Semantic search across the aggregated canon |
| `read_passage` | Read a specific text / volume |
| `get_parallels` | Cross-canon parallels (汉 ↔ 巴利 ↔ 藏) for a passage |
| `lookup_dictionary` | Term lookup across 32 dictionaries |
| `lookup_entity` | Knowledge-graph entity facts |
| `resolve_urn` | Resolve a FoJin URN to its source location |

Claude Desktop config and ChatGPT setup are in **[`mcp-server/README.md`](mcp-server/README.md)**. The server is a thin, read-only client: it holds no credentials, bundles no corpus, and only calls FoJin's public endpoints — its default target is `https://fojin.app/api`, overridable via `FOJIN_API_BASE_URL` to point at a self-hosted instance.

## Features

### Multi-Dimensional Search

Search across Buddhist canons by title, translator, catalog number, or full-text keyword. Powered by Elasticsearch with ICU tokenizer for multi-language support.

<p align="center"><img src="./docs/screenshots/search.png" alt="Search results for Avatamsaka Sutra" width="800"></p>

### Full-Text Reading

Read 8,900+ Buddhist texts with 23,500+ volumes of full content online. CBETA-style typography with intelligent verse/prose detection, paragraph reflow, and adjustable font size. Navigate by volume, scroll through content, and jump between related texts.

### Parallel Reading (30 Languages)

Compare translations side by side — Classical Chinese, Sanskrit, Pali, Tibetan, English, Japanese, Korean, Gandhari, and 21 more languages.

### Dictionary Lookup

32 authoritative dictionaries with 748,000+ entries across Chinese, Pali, Sanskrit, Tibetan, and English:

**Chinese Buddhist Dictionaries (14)**
- **NTI Reader** (佛学辞典) — 161K entries, Chinese↔English
- **Suihan Lu** (新集藏經音義隨函錄) — 72K entries, Tang dynasty phonetic glossary
- **Fo Guang** (佛光大辭典) — 32K entries
- **Ding Fubao** (丁福保佛学大辞典) — 31K entries
- **Yiqiejing Yinyi** (一切經音義, 慧琳音義) — 23K entries, Buddhist scriptural phonetics
- **Faxiang Dictionary** (法相辭典, 朱芾煌) — 15K entries, Yogācāra terminology
- **Zhonghua Encyclopedia** (中華佛教百科全書) — 6K entries
- **Common Buddhist Terms** (佛學常見詞彙, 陳義孝) — 6K entries
- **Agama Dictionary** (阿含辭典, 莊春江) — 5K entries
- **Fanfanyu** (翻梵語) — 4K entries, Sanskrit-Chinese translation glossary
- **Xu Yinyi** (續一切經音義, 希麟) — 2K entries
- **Yogācāra Glossary** (唯識名詞白話新解) — 2K entries
- **Sanzang Fashu** (三藏法數) — 1K entries
- **Buddhist Origins of Idioms** (俗語佛源) — 567 entries

**Pali Dictionaries (5)**
- **Digital Pali Dictionary** (DPD) — 89K entries, grammar + etymology + examples
- **NCPED** (New Concise Pali-English Dictionary) — 21K entries
- **PTS PED** (Pali Text Society) — 16K entries
- **Buddhadatta** (巴利語辭典, 達摩比丘中譯) — 11K entries, Pali→Chinese
- **SuttaCentral Glossary** — 6K entries

**Sanskrit Dictionaries (4)**
- **Apte** (Practical Sanskrit-English Dictionary) — 35K entries
- **Monier-Williams** (Sanskrit-English Dictionary) — 32K entries
- **Edgerton BHS** (Buddhist Hybrid Sanskrit Dictionary) — 18K entries
- **Fanyi Mingyi Ji** (翻譯名義集) — 1K entries

**Tibetan Dictionaries (2)**
- **Rangjung Yeshe** (Tibetan-English Dictionary) — 74K entries
- **Hopkins** (Tibetan-Sanskrit-English Dictionary) — 18K entries

**Multilingual Reference (4)**
- **Soothill-Hodous** (Chinese Buddhist Terms, Chinese↔English) — 17K entries
- **Mahāvyutpatti** (翻譯名義大集, Sanskrit↔Tibetan↔Chinese) — 9K entries
- **Nanshan Vinaya** (南山律学辞典) — 3K entries
- **Pentaglot** (五體清文鑑, Manchu-Mongolian-Tibetan-Chinese-Sanskrit) — 1K entries

**Specialized (3)**
- **Abhidharma Dictionary** (阿毗達磨辭典) — 1K entries
- **Tiantai Dictionary** (天台教學辭典) — 1K entries
- **DDB** (Digital Dictionary of Buddhism) — CJK Buddhist terminology

### Knowledge Graph

110,000+ entities (monasteries, persons, texts, schools, concepts) and 28,000+ relationships — including 22,000+ teacher-student lineage chains from the DILA Authority Database — visualized as an interactive force-directed graph. Click any node to explore connections.

### Trilingual Cross-Canon Parallel Reading (三语对读)

**The first LLM-driven cross-canon parallel reading system for Buddhist texts.** No other platform provides this: CBETA (汉文), SuttaCentral (Pali), and 84000 (Tibetan) each operate in their own language silo. FoJin bridges them via LLM-verified chunk-level alignment.

**Current coverage (3,000+ chunk-level alignments across 11 pair definitions):**

| Sutra / Corpus | Source | Target | Pairs | Type |
|---|---|---|---:|---|
| **《妙法蓮華經》Lotus Sutra** (2026-06-08) | T0262 罗什 (Chinese) | Toh 113 Kangyur (Tibetan) | **259** | 汉 ↔ 藏 |
| **《小品般若波羅蜜經》8,000-verse Prajñāpāramitā** (2026-06-09) | T0227 罗什 (Chinese) | Toh 11 Aṣṭasāhasrikā (Tibetan) | **127** | 汉 ↔ 藏 |
| 《維摩詰所說經》Vimalakīrti | T0475 罗什 (Chinese) | Toh 176 (Tibetan) | 20 | 汉 ↔ 藏 |
| 《般若波羅蜜多心經》Heart Sutra | T0252 (Chinese) | Toh 21 Kangyur (Tibetan) | 6 | 汉 ↔ 藏 |
| Mahāsatipaṭṭhāna Sutta 念处经 | MN 10 (Pali) | T0026 中阿含 (Chinese) | 50 | 巴 ↔ 汉 |
| Dhammacakkappavattana 转法轮经 | SN 56.11 (Pali) | T0099 杂阿含 (Chinese) | 17 | 巴 ↔ 汉 |
| Dhammapada 法句经 | T0210 (Chinese) | SC 26 vaggas (Pali) | 49 | 汉 ↔ 巴 |
| **Majjhima Nikāya ↔ 中阿含** | All MN suttas (Pali) | T0026 (Chinese) | ~1,800 | 巴 ↔ 汉 |
| **Dīgha Nikāya ↔ 长阿含** | All DN suttas (Pali) | T0001 (Chinese) | ~700 | 巴 ↔ 汉 |
| **Saṃyutta Nikāya 56 ↔ 杂阿含** | SN 56 suttas (Pali) | T0099 (Chinese) | ~150 | 巴 ↔ 汉 |
| **Aṅguttara Nikāya 4 ↔ 增一阿含** | AN 4 suttas (Pali) | T0125 (Chinese) | ~400 | 巴 ↔ 汉 |

Confidence distribution: all pairs ≥ 0.75. Hand-verified precision on the original MVP sample: **100%**. Mahāyāna 汉藏 batches: Lotus Sutra (2026-06-08) at $1.70 / 259 pairs (8.6% accept rate); 8,000-verse Prajñāpāramitā (2026-06-09) at $3.64 / 127 pairs (3.4% accept rate, lower because the sūtra's repetitive paratactic style yields fewer 1:1 chunk-level correspondences).

**How to use:**

1. **In AI Q&A** — When XiaoJin cites an aligned sutra, the citation drawer shows tabs `[ 汉文 ] [ 巴利 (5) ] [ 藏文 (3) ]`. Click a tab to see the corresponding passage in another canon, rendered with proper Devanagari / Tibetan fonts.

2. **In the reader** — Click the 🌐 **「多语对读」** (Multilingual Parallel) button in the toolbar. Default tab **「按经对读」** shows sutta-level parallels from SuttaCentral's authoritative Akanuma-style table (3,293 pairs covering all 4 Āgamas ↔ Nikāyas), with Pāli original + Sujato English previews and "read full text" links. Alternate tab **「按段对读」** retains the experimental embedding+LLM chunk-level alignment (pipeline-generated, known to have noise). The panel sits to the left of the AI reading panel; both can be open simultaneously and independently resized.

**Pipeline (`backend/scripts/build_alignments.py`):**

- pgvector top-20 candidate recall within target text's embeddings
- LLM verification (DeepSeek V3) returns `{is_parallel, confidence, reason}` JSON per candidate
- Pairs with `confidence ≥ 0.75` persisted to `alignment_pairs` with unique `(text_a, text_b)` chunk tuple for idempotent re-runs
- `$50` cost ceiling guard (actual MVP spend: **~$0.15**)
- Multi-target resolver supports cases where target is split across rows (e.g., SC Dhammapada's 26 separate vagga texts)

RAG layer automatically includes parallel_chunks in the LLM context when a retrieved chunk has alignments, so answers can naturally reference "the Pali version says…" without hallucinating.

**Growing the alignment set — the flywheel:** beyond the batch pipeline above, an *alignment flywheel* (`backend/app/services/alignment_flywheel.py`) mines new candidate parallels by expanding outward from already-verified pairs — neighbouring chunks tend to align too, so this is both fast and precise where blind nearest-neighbour search drowns in same-language matches. Candidates are staged for **human review** (admin UI at `/admin/alignment/review`) and only promoted into the ground-truth `alignment_pairs` once accepted (`method='flywheel-verified'`). Nothing is auto-promoted — human review is the precision gate — and each verified alignment makes the next round of mining better. A **margin-based candidate router** in `build_alignments.py` routes recalled candidates into auto-accept / LLM-verify / auto-reject bands by ratio-margin, cutting LLM cost while keeping auto-accept off by default so the precision guarantee holds.

**From chunks to sentences — the depth play:** verified chunk pairs seed **sentence-level alignment** (`backend/scripts/refine_sentence_alignments.py` + `services/sentence_align.py`): a pure-Python bertalign-style dynamic program subdivides each aligned paragraph into 1-1 / 1-2 / 2-1 sentence pairs over BGE-M3 cosine similarity, anchored to stable character offsets and stored in `sentence_alignments`. This backs precise 逐句对读 and cross-lingual sentence lookup. Two consumption surfaces already ship: **cross-lingual sentence search** (`GET /api/search/parallel-sentences` — query in Chinese, get aligned Sanskrit/Tibetan sentences over the ~896K-pair MITRA store) and a **versioned, license-stamped public dataset export** (`GET /exports/alignments.jsonl`) that turns the alignment corpus into a citable research artifact. Alignment quality is guarded by a dedicated **eval harness** (gold set + precision/recall/calibration metrics + regression gate) alongside the RAG eval, and MITRA cross-canon parallels feed the RAG context gated by a proxy quality score (`mitra_e_score`).

### AI Q&A — "XiaoJin"

**This is FoJin's core.** Ask questions in natural language; XiaoJin answers from canonical Buddhist texts using RAG (Retrieval-Augmented Generation) over 680K+ embedding vectors with an HNSW index for fast semantic search. Answers stay grounded because retrieval combines vector similarity, keyword reranking, and **root-sutra recall** (the sutra you asked about is always pulled into context), and every quoted passage is checked against the retrieved sources before it can become a clickable citation. Features include:

- Multi-turn conversation with context awareness
- Keyword + optional API cross-encoder **reranking** for higher answer quality
- **Clickable citations** in 【《经名》第N卷】 format — click to open a side drawer with surrounding context, plus **multi-language tabs for cross-canon parallels** when available (see Trilingual section above)
- **GFM markdown tables** — comparative answers (e.g., "Madhyamaka vs Yogācāra") render as proper tables instead of raw pipe syntax
- **Progressive follow-up suggestions** (concept → related texts → practice)
- **Smart data source recommendations** — when users ask about finding databases, AI automatically recommends relevant sources from 613 data sources via semantic similarity
- **Meta-question handling** — detects self-introduction queries ("who are you" / "what can you do") and skips RAG to give a clean functional overview, instead of randomly citing scriptures
- **Anti-hallucination citation rules** — the system prompt strictly forbids wrapping a text name in 【…】 unless that exact source appeared in the retrieved context, preventing broken citation links
- **Inline split-view in reader** — AI panel opens by default beside the text with a draggable divider; independent scrolling on each side, resizable width persisted to localStorage
- **"Ask XiaoJin" button** on the reader page — select text to ask about it
- **Tab key** cycles through suggested questions in the input box
- BYOK (Bring Your Own Key) support for multiple LLM providers

<p align="center"><img src="./docs/screenshots/ai-chat-answer.png" alt="AI Q&A answering about Xuanzang's disciples" width="800"></p>

### Verifiable answers — 每一句都能点回原典

Trust is the point. Every answer passes three **deterministic** guards before it reaches you:

- **Citation whitelist** — a 【《sutra》juan N】 citation is stripped or corrected unless that exact source was actually retrieved, so a citation link never points at something FoJin didn't read.
- **Quote verification** — text inside quote marks is checked to be a *verbatim* substring of the retrieved passage (traditional/simplified folded); a non-verbatim "quote" is **downgraded** to plain prose rather than passed off as scripture.
- **Trust state** — each answer is labelled `verified` / `citation_corrected` / `quote_relaxed` / `no_sources` so you can see how grounded it is.

Measured on the eval harness at temperature 0, the raw model is verbatim-faithful only ~11% of the time — but after the guards **~98% of served answers are trustworthy**: FoJin either points you to a real source or honestly hedges, and never fabricates scripture. The metric (`served_trustworthy_rate`) is tracked in `backend/eval/faithfulness.py` as a regression gate.

### Research Assistant (研究助手)

For multi-step questions a single search can't answer — *"how is śūnyatā treated across Prajñāpāramitā, Madhyamaka and Yogācāra, with cited cross-canon parallels?"* — the research assistant **plans** the question into steps, **retrieves** across the corpus, dictionaries and knowledge graph, then **synthesises** a grounded answer. The synthesis runs through the *same* citation guards as chat, so the agent can plan freely but **cannot cite what it didn't retrieve**. Available at `/research` (sign-in required); API at `POST /api/research/query`.

### Master Persona Mode (法师模式)

Select a specific Buddhist master to receive answers in their teaching style, grounded in their tradition's core scriptures. 15 historical masters available:

| Master | Tradition | Core Teachings |
|--------|-----------|----------------|
| 龙树 Nāgārjuna | 印度·中观 | 八不中道、缘起性空、二谛中道、戏论寂灭 |
| 智顗 Zhiyi | 天台宗 | 一念三千、三谛圆融、五时八教、止观双修 |
| 慧能 Huineng | 禅宗 | 直指人心、见性成佛、无念无相无住 |
| 玄奘 Xuanzang | 法相唯识宗 | 八识、三性、五位百法、转识成智 |
| 法藏 Fazang | 华严宗 | 法界缘起、四法界、十玄门、六相圆融 |
| 鸠摩罗什 Kumarajiva | 三论宗/中观 | 八不中道、缘起性空、不二法门 |
| 印光 Yinguang | 净土宗 | 信愿行、持名念佛、敦伦尽分 |
| 蕅益 Ouyi | 天台/净土·跨宗派 | 教宗天台行归净土、六信、性相融会 |
| 虚云 Xuyun | 禅宗·五宗兼嗣 | 参话头、起疑情、老实修行 |
| 米拉日巴 Milarepa | 藏传·噶举派 | 雪山闭关瑜伽士、那洛六法、以道歌说法 |
| 阿姜查 Ajahn Chah | 南传·泰国森林禅林派 | 正念、放下、朴素生活化教学 |
| 宗喀巴 Tsongkhapa | 藏传·格鲁派 | 菩提道次第、三主要道、应成中观 |
| 阿底峡 Atiśa Dīpaṃkara | 藏传·噶当派（印藏桥梁） | 菩提道灯论、三士道、七因果 |
| 觉音 Buddhaghosa | 南传·上座部论师 | 清净道论、戒定慧、七清净十六观智 |
| 马哈希 Mahasi Sayadaw | 南传·缅甸内观传统 | 标记现象法、腹部起伏、四念处密集禅修 |

Each master has a 100-150 line enriched system prompt with lineage, core doctrines, speaking style, teaching methods, key allusions, and terminology table. When a master is selected, RAG retrieval is **scoped to their core scriptures** (e.g., selecting Zhiyi only searches 《摩诃止观》《法华玄义》 etc.), providing more precise citations.

Powered by [Master-skill](https://github.com/xr843/Master-skill) — the open-source Buddhist master AI persona framework.

### Knowledge Graph Map (知识图谱地图)

Visualize 50,000+ geo-enabled Buddhist entities on an interactive world map — monasteries, historical places, persons, and schools. Built with Deck.GL + MapLibre.

- **Entity types**: Monasteries (green), Places (purple), Persons (red), Schools (blue)
- **Lineage arcs**: Toggle 8,000+ teacher-student lineage relations as animated arcs on the map
- **Chinese-only filter**: Quickly filter to show only Chinese-named entities
- **Entity search**: Find entities by name with simplified/traditional Chinese conversion (OpenCC)
- **Interactive tooltips**: Hover to see metadata, country flags, and source attribution

### Activity Feed (佛学动态)

Track real-time updates from 613 data sources — new texts added, translation releases, manuscript scans, and schema changes. Includes academic content aggregation and platform-wide activity summary.

### Similar Passages Discovery

When reading any text, the sidebar automatically finds semantically similar passages from other texts using pgvector cosine similarity. Discover cross-textual parallels, related commentaries, and thematic connections across the entire canon.

### Timeline & Statistics Dashboard

Visualize Buddhist textual history with interactive D3 charts — dynasty distribution, translation trends, language breakdown, category treemap, and top translators. Toggle between scholarly and popular presentation modes.

### Collections, Bookmarks & Annotations

Save texts to personal collections, bookmark specific passages, and add annotations for study and research.

### Citation Export

Export citations in BibTeX, RIS, and APA formats for academic papers and reference managers.

### Multi-Language UI

Available in 9 languages: Simplified Chinese, Traditional Chinese, English, Japanese, Korean, Thai, Vietnamese, Sinhala, and Burmese.

## Data Sources

<p align="center"><img src="./docs/screenshots/sources.png" alt="613 data sources from 30 countries" width="800"></p>

FoJin aggregates data from major Buddhist digital projects worldwide. Sources are categorized by research field (Han, Theravada, Tibetan, Sanskrit, Dunhuang, Art, Dictionary, Digital Humanities) and filterable by region, language, and type:

| Source | Content | Languages |
|--------|---------|-----------|
| [CBETA](https://cbeta.org) | Chinese Buddhist Canon | Classical Chinese |
| [SuttaCentral](https://suttacentral.net) | Early Buddhist Texts | Pali, Chinese, English |
| [84000](https://84000.co) | Tibetan Buddhist Canon | Tibetan, English, Sanskrit |
| [BDRC](https://bdrc.io) | Tibetan manuscripts (IIIF) | Tibetan |
| [SAT](https://21dzk.l.u-tokyo.ac.jp/SAT/) | Taisho Tripitaka | Chinese, Japanese |
| [DILA](https://authority.dila.edu.tw) | Authority databases (persons, places, catalogs) | Multi-language |
| [GRETIL](http://gretil.sub.uni-goettingen.de) | Sanskrit e-texts | Sanskrit |
| [DSBC](https://www.dsbcproject.org) | Digital Sanskrit Buddhist Canon | Sanskrit |
| [Gandhari.org](https://gandhari.org) | Gandhari manuscripts | Gandhari |
| [VRI Tipitaka](https://tipitaka.org) | Pali Canon (Chattha Sangayana) | Pali |
| [Korean Tripitaka](http://kb.sutra.re.kr) | Goryeo Tripitaka | Chinese, Korean |
| + 602 more... | | |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, Ant Design 5, Zustand, TanStack Query, D3.js, Deck.GL + MapLibre (geo map) |
| Backend | FastAPI, SQLAlchemy (async), Pydantic v2, SSE streaming |
| Database | PostgreSQL 15 + pgvector (HNSW index) + pg_trgm |
| Search | Elasticsearch 8 (ICU tokenizer) |
| Cache | Redis 7 |
| AI | RAG (680K+ vectors, BGE-M3, HNSW) + 14 master personas + multi-provider LLM (OpenAI/Anthropic/DeepSeek/DashScope/Gemini/+10 more) + deterministic citation/quote guards |
| Integration | MCP server ([`fojin-mcp`](https://pypi.org/project/fojin-mcp/), stdio) + public REST API with OpenAPI/Swagger docs + cross-canon URN scheme |
| Deploy | Docker Compose, Nginx (gzip, security headers), Cloudflare CDN |
| CI | GitHub Actions (lint, test, security scan) |

## Architecture

```
                  +-------------+
                  | Cloudflare  |  (CDN, SSL, DDoS protection)
                  +------+------+
                         |
                  +------+------+
                  |   Nginx     |  (gzip, security headers, static cache)
                  +------+------+
                         |
             +-----------+-----------+
             |                       |
       +-----+------+         +-----+------+
       |  React 18   |         |  FastAPI    |
       |  Vite + D3  |         |  async SSE  |
       +-------------+         +------+------+
                                      |
                   +--------+---------+---------+
                   |        |         |         |
             +-----+--+ +--+----+ +--+---+ +---+--------+
             | PG 15   | | ES 8  | |Redis | | LLM APIs   |
             | pgvector | | ICU   | |cache | | (multi-    |
             | HNSW idx | |       | |      | |  provider) |
             +---------+ +-------+ +------+ +------------+
```

## Development

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev

# Tests
cd backend && pytest tests/ -q
```

## Security

- Non-root containers (backend: `app`, frontend: `nginx`)
- Multi-stage Docker builds (no build tools in production)
- Internal services (Postgres, Redis, Elasticsearch, backend, Umami) bound to `127.0.0.1` only
- Memory/CPU limits per container
- CSP, X-Frame-Options, X-Content-Type-Options headers
- Query length limits on all search parameters
- JWT with 8h expiry, production requires strong secret

### Self-hosting privacy defaults

- **No analytics phone-home.** The Umami tracking script is opt-in via build-time `VITE_UMAMI_URL` + `VITE_UMAMI_WEBSITE_ID`; if either is unset, the frontend ships without telemetry.
- **LLM / embedding traffic is upstream by default.** Stock config calls DeepSeek + SiliconFlow with your platform key — user questions go there. Point `LLM_API_URL` / `EMBEDDING_API_URL` at a local OpenAI-compatible server (vLLM, Ollama, LM Studio) for a fully offline setup, or have each user provide their own key via the in-app BYOK flow.
- **The frontend container binds to `127.0.0.1` by default** (set via `FRONTEND_BIND`), so out of the box it's reachable only from the host — put an authenticated reverse proxy or CDN in front of it as the public entry. If you need direct LAN/remote access without a proxy, set `FRONTEND_BIND=0.0.0.0`; note that Docker publishes ports through its own iptables rules that bypass host firewalls like `ufw`, so anyone who can reach the host on that port hits your instance.

See [SECURITY.md](SECURITY.md) for the full picture.

## Contributing

Contributions are welcome! Whether it's adding a new data source, improving search, fixing bugs, or translating the UI — we'd love your help.

1. Fork the repository
2. Create your feature branch (`git checkout -b feat/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feat/amazing-feature`)
5. Open a Pull Request

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

## Roadmap

- [x] Citation export (BibTeX, RIS, APA)
- [x] Mobile-responsive reader
- [x] Public REST API with rate limiting
- [x] User annotations
- [x] Community-contributed data sources
- [x] Internationalization (i18n) — 9 UI languages
- [x] Embedding-based semantic search (680K+ vectors, HNSW index)
- [x] AI Q&A with RAG, multi-turn context, and streaming
- [x] Similar passages discovery (cross-text semantic matching)
- [x] Timeline visualization and statistics dashboard
- [x] User feedback system and notification center
- [x] Admin dashboard (user management, platform analytics)
- [x] API documentation (OpenAPI/Swagger at `/docs`, ReDoc at `/redoc`)
- [x] AI answer reranking (keyword + optional API cross-encoder)
- [x] Clickable citation links in AI answers
- [x] Progressive follow-up suggestions after AI answers
- [x] "Ask XiaoJin" floating button on reader page
- [x] Tab key to cycle through suggested questions
- [x] CBETA-style text layout with verse/prose detection
- [x] Auto database migration on Docker startup
- [x] AI answer rating (thumbs up/down) for quality tracking
- [x] Research field filtering for data sources (8 categories)
- [x] Admin feedback reply with notification system
- [x] AI-powered data source recommendations in chat (semantic similarity)
- [x] DILA Authority lineage import (22K+ teacher-student relations)
- [x] DILA catalog associations (contributors, places for 2,300+ texts)
- [x] Nanshan Vinaya Dictionary (3,200+ Buddhist precept terms)
- [x] CBETA full-text import — Taishō (T) + Xuzangjing (X): 3,600+ texts, 143M characters, 432K embedding vectors
- [x] Dictionary expansion — 32 dictionaries, 748K entries (DPD, Apte, Mahāvyutpatti, Buddhadatta, Pentaglot, buddhaspace 7 dicts)
- [x] Master Persona Mode — 14 Buddhist masters with tradition-scoped RAG (powered by [Master-skill](https://github.com/xr843/Master-skill))
- [x] Knowledge Graph Map — 50K+ geo entities, Deck.GL + MapLibre, lineage arcs
- [x] Activity Feed — real-time source update tracking, academic feeds
- [x] Inline split-view AI reader panel with draggable divider and independent scrolling
- [x] AI panel auto-open in reader for one-click access to interpretation
- [x] Meta-question detection in chat — recognizes "who are you / what can you do" and skips RAG
- [x] **Trilingual cross-canon parallel reading** — 11 pair definitions, 3,000+ LLM-verified chunk alignments across CBETA / SuttaCentral / 84000 (incl. Lotus Sutra 法华 ↔ Toh 113, 8,000-verse Prajñāpāramitā 小品般若 ↔ Toh 11, the full Āgama ↔ Nikāya corpus, and the original 5 MVP classics)
- [x] Chat citation drawer with multi-language tabs (汉 / 巴 / 藏 side-by-side)
- [x] Reader "多语对读" inline sidebar — dual tabs: sutta-level SC-authoritative parallels + legacy chunk-level RAG alignment; coexists with AI panel, independent drag-resize
- [x] GFM markdown tables in AI answers (remark-gfm) — comparative responses render as proper tables
- [x] Anti-hallucination citation rules (Rule 4/4b) — forbid wrapping non-retrieved sutra names in 【…】
- [x] Server-side SEO meta injection for `/texts/{id}` pages — proper `<title>` / `<description>` per sutra for search engines (SPA route crawlability)
- [x] **Deterministic answer verifiability** — citation whitelist + verbatim-quote downgrade + per-answer trust state; `served_trustworthy_rate` ~98% at temp 0 as an eval regression gate
- [x] **Cross-canon URN scheme** — stable, resolvable passage identifiers (`fojin:cbeta/T0001.1`) interoperable with CBETA / SuttaCentral / 84000 / GRETIL / VRI
- [x] **MCP server — published to PyPI as [`fojin-mcp`](https://pypi.org/project/fojin-mcp/)** — 6 read-only, URN-addressable tools; callable from Claude Desktop / ChatGPT
- [x] **Agentic research assistant** (`/research`) — plan → retrieve (corpus + dictionary + KG) → grounded synthesis behind the same citation guards
- [x] **Alignment flywheel** — anchor-expansion candidate mining + human-review promotion (admin UI at `/admin/alignment/review`) into ground-truth alignments
- [x] **Sentence-level cross-canon alignment** — bertalign-style DP over BGE-M3 embeddings subdivides verified chunk pairs into aligned sentence pairs (`sentence_alignments`); pure-Python, no new deps
- [x] **Margin-based candidate router** — ratio-margin bands (auto-accept / LLM-verify / auto-reject) in the alignment builder cut LLM cost while preserving the 100%-precision guarantee (auto-accept off by default)
- [x] **Alignment-quality eval harness** — gold set + deterministic precision/recall/calibration metrics + regression gate mirroring the RAG eval
- [x] **MITRA cross-lingual parallels in RAG** — ~896K Skt/Tib ↔ 汉 sentence pairs gated by a proxy quality score (`mitra_e_score`, NULL-permissive)
- [x] Cross-lingual search (query in Chinese, find Sanskrit/Pali/Tibetan results) — over MITRA sentence parallels (`GET /api/search/parallel-sentences`)
- [x] Open alignment dataset export — versioned, license-stamped JSONL with provenance + `GET /exports/alignments.jsonl` streaming endpoint
- [ ] Trilingual MVP v1.1 — expand to 20+ sutras (Lotus, Avataṃsaka, Madhyamakakārikā, Laṅkāvatāra, full Āgama↔Nikāya)
- [ ] Reader 逐句对读 (sentence-level parallel reading UI) — backend contract shipped (`GET /alignment/sentences/...`, ships dark behind `enable_sentence_parallels`); frontend pending prod sentence data
- [ ] Topic ontology browsing page
- [ ] OCR pipeline for scanned texts
- [ ] Collaborative annotation sharing
- [ ] Integration with Zotero and reference managers

## License

[Apache License 2.0](LICENSE) — applies to FoJin source code only. Third-party data sources retain their own licenses (CC BY-NC-SA, CC0, CC BY-NC-ND, etc.). See [NOTICE](NOTICE) for details.

## Acknowledgments

FoJin is built on the generous work of the global Buddhist digital humanities community. Special thanks to:

- [CBETA](https://cbeta.org) — Chinese Buddhist Electronic Text Association
- [SuttaCentral](https://suttacentral.net) — Early Buddhist Texts
- [BDRC](https://bdrc.io) — Buddhist Digital Resource Center
- [84000](https://84000.co) — Translating the Words of the Buddha
- [SAT](https://21dzk.l.u-tokyo.ac.jp/SAT/) — SAT Daizokyo Text Database
- All other data source providers listed in the [Sources page](https://fojin.app/sources)

## Community

- [LINUX DO](https://linux.do) — Thanks to the LINUX DO community for support and feedback

## Related Projects

- [Master-skill](https://github.com/xr843/Master-skill) — Buddhist master AI persona framework (powers FoJin's master mode)
- [The Open Buddhist University](https://buddhistuniversity.net) — Free courses, books, and encyclopaedia for Buddhist studies

---

<div align="center">

**If FoJin is useful for your research, please consider giving it a star!**

[Discussions](https://github.com/xr843/fojin/discussions) &nbsp;&middot;&nbsp; [Issues](https://github.com/xr843/fojin/issues) &nbsp;&middot;&nbsp; [Contributing](CONTRIBUTING.md) &nbsp;&middot;&nbsp; [contact@fojin.app](mailto:contact@fojin.app)

Made with care for the Buddhist studies community.

</div>
