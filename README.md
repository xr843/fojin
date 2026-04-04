<div align="center">

# FoJin 佛津

### The World's Encyclopedic Buddhist Digital Text Platform

**503 sources. 30 languages. 30 countries. 23,500+ full-text volumes. One search.**

Aggregating the world's Buddhist digital heritage — 10,500+ texts with 23,500+ volumes of full content in Pali, Classical Chinese, Tibetan, and Sanskrit from 503 data sources — with CBETA-style reading, AI-powered Q&A (RAG + reranking + citations + data source recommendations), knowledge graph with 31K+ entities and 28K+ relations (including 23K teacher-student lineage chains), 32 dictionaries with 748K entries across 6 languages, timeline visualization, collections, citations, annotations, bookmarks, and multi-language parallel reading.

[Live Demo](https://fojin.app) &nbsp;&middot;&nbsp; [API Docs](https://fojin.app/docs) &nbsp;&middot;&nbsp; [中文文档](./docs/README_zh.md) &nbsp;&middot;&nbsp; [Discussions](https://github.com/xr843/fojin/discussions) &nbsp;&middot;&nbsp; [Discord](https://discord.gg/76SZeuJekq) &nbsp;&middot;&nbsp; [Report Bug](https://github.com/xr843/fojin/issues)

[![CI](https://github.com/xr843/fojin/actions/workflows/ci.yml/badge.svg)](https://github.com/xr843/fojin/actions/workflows/ci.yml)
[![Security Scan](https://github.com/xr843/fojin/actions/workflows/security.yml/badge.svg)](https://github.com/xr843/fojin/actions/workflows/security.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/xr843/fojin?style=social)](https://github.com/xr843/fojin)

![FoJin — Global Buddhist Digital Text Platform](./docs/screenshots/hero.png)

</div>

---

## Why FoJin?

Buddhist texts are scattered across hundreds of databases worldwide — CBETA, SuttaCentral, BDRC, SAT, 84000, GRETIL, and many more. Each has different interfaces, languages, and data formats. Researchers spend more time *finding* texts than *reading* them.

**FoJin solves this.** It aggregates 503 sources into a single, searchable platform with features no other tool provides:

| What you need | How FoJin helps |
|---|---|
| Find a sutra across databases | **Multi-dimensional search** across 10,500+ texts from 503 sources |
| Read the full text online | **8,900+ texts** with 23,500+ volumes of full content, CBETA-style layout |
| Compare translations | **Parallel reading** in 30 languages side by side |
| Look up Buddhist terms | **32 dictionaries**, 748K entries (Chinese/Sanskrit/Pali/Tibetan/English) |
| Explore relationships | **Knowledge graph** with 31K+ entities and 28K+ relations (23K lineage chains) |
| Discover similar texts | **Semantic similarity** powered by 678K+ embedding vectors (pgvector + HNSW) |
| View original manuscripts | **IIIF manuscript viewer** connected to BDRC and more |
| Ask questions about texts | **AI Q&A** ("XiaoJin") with RAG, reranking, clickable citations, and follow-up suggestions |
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
docker exec fojin-backend python -m scripts.generate_embeddings --source cbeta

# Import SuttaCentral Early Buddhist Texts
docker exec fojin-backend python scripts/import_suttacentral.py

# See all available importers
ls backend/scripts/import_*.py
```

Each importer downloads data directly from the original source (CBETA, SuttaCentral, etc.) — no data is bundled in this repository.

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

31,000+ entities (persons, monasteries, texts, schools, concepts) and 28,000+ relationships — including 23,000 teacher-student lineage chains from the DILA Authority Database — visualized as an interactive force-directed graph. Click any node to explore connections.

### AI Q&A — "XiaoJin"

Ask questions in natural language. XiaoJin answers based on canonical Buddhist texts using RAG (Retrieval-Augmented Generation) with 678K+ embedding vectors and HNSW index for fast semantic search. Features include:

- Multi-turn conversation with context awareness
- Keyword + optional API cross-encoder **reranking** for higher answer quality
- **Clickable citations** in 【《经名》第N卷】 format — click to jump to the text reader
- **Progressive follow-up suggestions** (concept → related texts → practice)
- **Smart data source recommendations** — when users ask about finding databases, AI automatically recommends relevant sources from 503 data sources via semantic similarity
- **"Ask XiaoJin" button** on the reader page — select text to ask about it
- **Tab key** cycles through suggested questions in the input box
- BYOK (Bring Your Own Key) support for multiple LLM providers

<p align="center"><img src="./docs/screenshots/ai-chat-answer.png" alt="AI Q&A answering about Xuanzang's disciples" width="800"></p>

### Similar Passages Discovery

When reading any text, the sidebar automatically finds semantically similar passages from other texts using pgvector cosine similarity. Discover cross-textual parallels, related commentaries, and thematic connections across the entire canon.

### Timeline & Statistics Dashboard

Visualize Buddhist textual history with interactive D3 charts — dynasty distribution, translation trends, language breakdown, category treemap, and top translators. Toggle between scholarly and popular presentation modes.

### Collections, Bookmarks & Annotations

Save texts to personal collections, bookmark specific passages, and add annotations for study and research.

### Citation Export

Export citations in BibTeX, RIS, and APA formats for academic papers and reference managers.

### Manuscript Viewer

Browse digitized manuscripts and rare editions from BDRC and other institutions via IIIF protocol.

### Multi-Language UI

Available in 9 languages: Simplified Chinese, Traditional Chinese, English, Japanese, Korean, Thai, Vietnamese, Sinhala, and Burmese.

## Data Sources

<p align="center"><img src="./docs/screenshots/sources.png" alt="503 data sources from 30 countries" width="800"></p>

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
| + 492 more... | | |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, Ant Design 5, Zustand, TanStack Query, D3.js |
| Backend | FastAPI, SQLAlchemy (async), Pydantic v2, SSE streaming |
| Database | PostgreSQL 15 + pgvector (HNSW index) + pg_trgm |
| Search | Elasticsearch 8 (ICU tokenizer) |
| Cache | Redis 7 |
| AI | RAG (678K+ text vectors + 503 source vectors, BGE-M3 embeddings, HNSW) + multi-provider LLM (OpenAI/DashScope/DeepSeek/SiliconFlow) |
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
- Internal services bound to `127.0.0.1` only
- Memory/CPU limits per container
- CSP, X-Frame-Options, X-Content-Type-Options headers
- Query length limits on all search parameters
- JWT with 8h expiry, production requires strong secret

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
- [x] Embedding-based semantic search (678K+ vectors, HNSW index)
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
- [x] DILA Authority lineage import (23K teacher-student relations)
- [x] DILA catalog associations (contributors, places for 2,300+ texts)
- [x] Nanshan Vinaya Dictionary (3,200+ Buddhist precept terms)
- [x] CBETA full-text import — Taishō (T) + Xuzangjing (X): 3,600+ texts, 143M characters, 432K embedding vectors
- [x] Dictionary expansion — 32 dictionaries, 748K entries (DPD, Apte, Mahāvyutpatti, Buddhadatta, Pentaglot, buddhaspace 7 dicts)
- [ ] Topic ontology browsing page
- [ ] Cross-lingual search (query in Chinese, find Sanskrit/Pali/Tibetan results)
- [ ] Open data export (JSON/CSV for researchers)
- [ ] MCP Server for AI assistant integration
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

- [The Open Buddhist University](https://buddhistuniversity.net) — Free courses, books, and encyclopaedia for Buddhist studies

---

<div align="center">

**If FoJin is useful for your research, please consider giving it a star!**

[Discussions](https://github.com/xr843/fojin/discussions) &nbsp;&middot;&nbsp; [Issues](https://github.com/xr843/fojin/issues) &nbsp;&middot;&nbsp; [Contributing](CONTRIBUTING.md) &nbsp;&middot;&nbsp; [contact@fojin.app](mailto:contact@fojin.app)

Made with care for the Buddhist studies community.

</div>
