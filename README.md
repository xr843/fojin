<div align="center">

# FoJin 佛津

### The World's Encyclopedic Buddhist Digital Text Platform

**409 sources. 29 languages. 27 countries. One search.**

Aggregating the world's Buddhist digital heritage — from the Chinese Tripitaka to Sanskrit manuscripts, Pali suttas to Tibetan texts — with full-text reading, AI-powered Q&A, knowledge graph, and multi-language parallel reading.

[Live Demo](https://fojin.app) &nbsp;&middot;&nbsp; [中文文档](./docs/README_zh.md) &nbsp;&middot;&nbsp; [Report Bug](https://github.com/xr843/fojin/issues)

<!-- TODO: Uncomment after first push
[![CI](https://github.com/xr843/fojin/actions/workflows/ci.yml/badge.svg)](https://github.com/xr843/fojin/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
-->

</div>

---

## Why FoJin?

Buddhist texts are scattered across hundreds of databases worldwide — CBETA, SuttaCentral, BDRC, SAT, 84000, GRETIL, and many more. Each has different interfaces, languages, and data formats. Researchers spend more time *finding* texts than *reading* them.

**FoJin solves this.** It aggregates 409+ sources into a single, searchable platform with features no other tool provides:

| What you need | How FoJin helps |
|---|---|
| Find a sutra across databases | **Federated search** across local index + 728K records from DianJin |
| Read the full text online | **4,488 fascicles** available for online reading |
| Compare translations | **Parallel reading** in 29 languages side by side |
| Look up Buddhist terms | **6 dictionaries**, 237K entries (Chinese/Sanskrit/Pali/English) |
| Explore relationships | **Knowledge graph** with 9,600+ entities and 3,800+ relations |
| View original manuscripts | **IIIF manuscript viewer** connected to BDRC and more |
| Ask questions about texts | **AI Q&A** ("XiaoJin") grounded in 11M characters of canonical text |

## Quick Start

```bash
git clone https://github.com/xr843/fojin.git
cd fojin
cp .env.example .env
docker compose up -d
```

Then visit: **http://localhost:3000**

> API docs at http://localhost:8000/docs

## Features

### Multi-Dimensional Search

Search across Buddhist canons by title, translator, catalog number, or full-text keyword. Federated search combines local Elasticsearch results with 728,000 records from the DianJin platform (Tsinghua/CNKI).

### Full-Text Reading

Read 4,488 fascicles of Buddhist texts online. Navigate by volume, scroll through content, and jump between related texts.

### Parallel Reading (29 Languages)

Compare translations side by side — Classical Chinese, Sanskrit, Pali, Tibetan, English, Japanese, Korean, Gandhari, and 21 more languages.

### Dictionary Lookup

6 authoritative dictionaries with 237,593 entries:
- **DDB** (Digital Dictionary of Buddhism)
- **SuttaCentral Glossary** (Pali)
- **NCPED** (New Concise Pali-English Dictionary)
- **NTI** (Nan Tien Institute Buddhist Dictionary)
- **Edgerton BHS** (Buddhist Hybrid Sanskrit Dictionary)
- **Monier-Williams** (Sanskrit-English Dictionary)

### Knowledge Graph

9,600+ entities (persons, monasteries, texts, schools) and 3,800+ relationships, visualized as an interactive force-directed graph. Click any node to explore connections.

### AI Q&A — "XiaoJin"

Ask questions in natural language. XiaoJin answers based on canonical Buddhist texts (38 core sutras, ~11M characters) using RAG (Retrieval-Augmented Generation). Every answer includes citations to the source text.

### Manuscript Viewer

Browse digitized manuscripts and rare editions from BDRC and other institutions via IIIF protocol.

## Data Sources

FoJin aggregates data from major Buddhist digital projects worldwide:

| Source | Content | Languages |
|--------|---------|-----------|
| [CBETA](https://cbeta.org) | Chinese Buddhist Canon | Classical Chinese |
| [SuttaCentral](https://suttacentral.net) | Early Buddhist Texts | Pali, Chinese, English |
| [84000](https://84000.co) | Tibetan Buddhist Canon | Tibetan, English, Sanskrit |
| [BDRC](https://bdrc.io) | Tibetan manuscripts (IIIF) | Tibetan |
| [SAT](https://21dzk.l.u-tokyo.ac.jp/SAT/) | Taisho Tripitaka | Chinese, Japanese |
| [GRETIL](http://gretil.sub.uni-goettingen.de) | Sanskrit e-texts | Sanskrit |
| [DSBC](https://www.dsbcproject.org) | Digital Sanskrit Buddhist Canon | Sanskrit |
| [Gandhari.org](https://gandhari.org) | Gandhari manuscripts | Gandhari |
| [VRI Tipitaka](https://tipitaka.org) | Pali Canon (Chattha Sangayana) | Pali |
| [Korean Tripitaka](http://kb.sutra.re.kr) | Goryeo Tripitaka | Chinese, Korean |
| [DianJin](https://guji.cckb.cn) | Pan-Chinese classics (federated) | Chinese |
| + 398 more... | | |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, Ant Design 5, Zustand, TanStack Query |
| Backend | FastAPI, SQLAlchemy (async), Pydantic v2 |
| Database | PostgreSQL 15 + pgvector + pg_trgm |
| Search | Elasticsearch 8 (ICU tokenizer) |
| Cache | Redis 7 |
| AI | Dify + RAG (vector + keyword dual retrieval) |
| Deploy | Docker Compose, Nginx (gzip_static, security headers) |
| CI | GitHub Actions |

## Architecture

```
                    +-----------+
                    |  Nginx    |  (gzip, security headers, static cache)
                    +-----+-----+
                          |
              +-----------+-----------+
              |                       |
        +-----+-----+          +-----+-----+
        |  React 18  |          |  FastAPI   |
        |  (Vite)    |          |  (async)   |
        +------------+          +-----+------+
                                      |
                    +---------+-------+---------+
                    |         |       |         |
              +-----+   +----+--+ +--+---+ +---+----+
              | PG 15 |  | ES 8  | |Redis | | Dify   |
              |pgvector|  | ICU  | |cache | | RAG/AI |
              +--------+  +------+ +------+ +--------+
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

- [ ] OCR pipeline for scanned texts
- [ ] User annotations and collaborative notes
- [ ] Citation export (BibTeX, Chicago, MLA)
- [ ] Mobile-responsive reader
- [ ] Public REST API with rate limiting
- [ ] Embedding-based semantic search
- [ ] Community-contributed data sources

## License

[Apache License 2.0](LICENSE) — free for academic and commercial use.

## Acknowledgments

FoJin is built on the generous work of the global Buddhist digital humanities community. Special thanks to:

- [CBETA](https://cbeta.org) — Chinese Buddhist Electronic Text Association
- [SuttaCentral](https://suttacentral.net) — Early Buddhist Texts
- [BDRC](https://bdrc.io) — Buddhist Digital Resource Center
- [84000](https://84000.co) — Translating the Words of the Buddha
- [SAT](https://21dzk.l.u-tokyo.ac.jp/SAT/) — SAT Daizokyo Text Database
- [DianJin / CNKI](https://guji.cckb.cn) — Chinese Classic Texts Platform
- All other data source providers listed in the [Sources page](https://fojin.app/sources)

---

<div align="center">

**If FoJin is useful for your research, please consider giving it a star!**

Made with care for the Buddhist studies community.

</div>
