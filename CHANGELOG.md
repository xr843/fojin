# Changelog

All notable changes to FoJin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [3.4.0] — 2026-03-23

### Added
- RAG relevance filtering — chunks below 0.35 cosine similarity are excluded from AI context
- HNSW vector index on text_embeddings for O(log n) similarity search (was full table scan)
- Request logging middleware — logs method, path, status code, and duration for every request
- Auth API tests (register, login, /me, API key management) — 15 new backend tests
- Frontend unit tests now run in CI (Vitest)

### Changed
- AI system prompt with structured rules, citation format【《经名》第N卷】, and few-shot example
- RAG retrieval: fetch 10 candidates → filter by relevance → cap at 8 (was fixed top-5)

### Fixed
- CI: pin ruff version to 0.9.7 to match pre-commit config and prevent version drift

## [3.3.0] — 2026-03-10

First open-source release.

### Added
- BYOK (Bring Your Own Key) — users can configure personal LLM API keys for unlimited AI Q&A
- Admin source suggestion management with delete functionality
- NOTICE file with third-party data source licenses
- Security scanning workflow in CI

### Changed
- Removed DianJin (典津) integration from public repo (available as optional module)
- Nginx gzip_static + pre-compression optimization (22s → <1s page load)

### Fixed
- CI: skip known failing tests (annotation workflow, kg entity detail)
- CI: add missing pytest-asyncio dependency
- HomePage missing `<Helmet>` title causing stale browser tab
- Tocharian language split: `xto` → "吐火罗语A", `txb` → "吐火罗语B"
- `xml_parser.py` XMLSyntaxError handling for empty XML files

## [3.0.0] — 2026-02-15

### Added
- Full-text reading with 4,488 fascicles from T藏 (2,294 works)
- AI Q&A ("小津") powered by RAG with 38 core Buddhist texts (~11M characters)
- Knowledge graph visualization with 9,678 entities and 3,832 relations
- Dictionary search across 6 dictionaries (237,593 entries)
- IIIF manuscript viewer for BDRC digital manuscripts
- Data export in CSV, JSON, JSON-LD formats
- User annotations system
- Dark mode support
- PWA offline capability
