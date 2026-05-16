# Changelog

All notable changes to FoJin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Data-source health monitoring. `scripts/health_check_sources.py` probes every active source's `base_url` and records a `health_status` verdict (`ok` / `degraded` / `cert_invalid` / `unreachable` / `moved`) plus `health_checked_at`. The Sources page now shows a warning badge on cards whose source has moved, is unreachable, has an invalid TLS certificate, or returns HTTP errors — healthy sources stay unbadged. Redirects are followed by hand with a per-hop public-IP check so a hijacked source URL cannot turn the cron into an SSRF against internal services. Designed to run from cron; busts the sources-list cache after writing so a stale verdict survives at most one cache TTL. Builds on the `health_status` column added in migration 0132.
- `data_sources.health_detail` (migration 0136) — the health check now records actionable context for the latest probe: the redirect target for a `moved` source, the failure reason otherwise. A `moved` source's badge tooltip surfaces where it relocated to, so the verdict can be acted on instead of just observed.

### Changed
- Default DeepSeek model alias `deepseek-chat` → `deepseek-v4-flash` (legacy ID still works as alias). Production `LLM_MODEL` upgraded to `deepseek-v4-pro` to leverage 75% promotional pricing through 2026-05-31; revisit before promo ends to avoid 4× cost increase.
- Updated `build_alignments.py` price table with `deepseek-v4-flash` ($0.28/1M output) and `deepseek-v4-pro` ($0.87/1M output, promo).

### Fixed
- Data-source health check no longer badges healthy sources. A `403` / `401` / `429` response means the server answered — the site is up, it just won't serve an automated probe (bot protection, datacenter-IP blocks, auth walls). These now classify as `ok` instead of `degraded`; only `404` / `410` (page genuinely gone) stay `degraded`. The first audit run had wrongly flagged ~36 healthy major sources (idp.bl.uk, HathiTrust, loc.gov, the Tsadra ecosystem, Rubin Museum, …).
- Health check no longer reports a same-site sub-domain restructure as `moved`. `read.84000.co → 84000.co` and `collections.vam.ac.uk → vam.ac.uk` are reorganisations by the same operator, not relocations; `moved` is now reserved for a genuine cross-site redirect.
- `base_url` corrected for 8 relocated sources (migration 0137). Two dead sources retired: `suttaworld` (domain lapsed, now redirects to a gambling site) and `deerpark-ai` (the AI Q&A product is gone; its domain now redirects into `deerpark.app`, already catalogued separately).
- Four more dead sources retired (migration 0138), found by a content audit fetching homepage titles: `gandhari-scrolls` (ebmp.org sold off — "Sold by Seo.Domains") and `51shu` / `shu-fo` / `xuefo` (domains now serve an empty-host placeholder page). These answer HTTP 200, so the reachability cron could not catch them.
- `base_url` corrected for 3 sources whose institutions are alive but whose pages relocated (migration 0139): `sotozen-global` → `www.sotozen.com/eng/`, `dhammachai-tipitaka` → `www.dhammachaitipitaka.org/`, `komazawa-zenpon` → the Komazawa 電子貴重書庫 repository.
- 40 new data sources added + 2 reactivated (migration 0140) from a four-agent web sweep partitioned by tradition (CJK / Tibetan / Theravada / Sanskrit-academic-AI). ~80 raw candidates were deduped against the catalog (~15 already present under another code) and every survivor URL re-verified live (4 cut, 2 held). Two — `iriz-hanazono` and `read-workbench` — were found already present as inactive rows (hosts had gone down); both are now re-verified live and reactivated (`read-workbench` base_url corrected to `readworkbench.org`). Highlights: Vietnamese Buddhist libraries (Thư Viện Hoa Sen, HCMC Buddhist Research Institute), Japanese Pure Land / Shin sect canon databases, e-Museum, the Tsurumi Zen archive, Tibetan resources (RET journal, Steinert dictionary, Nitartha Digital Library, Rinchen Terdzö, Nekhor sacred-sites), SE Asian manuscript collections, museum open-access catalogs (British Museum, LACMA, Walters, Newark), and Buddhist NLP datasets/tools.
- Dictionary browse mode (`/api/dictionary/search/grouped` with `q=*`) now resolves `source.code → source_id` before the entry query so the planner can use the new `(source_id, headword)` composite index instead of walking the full headword btree. Foguang dictionary (32k entries / 360k total): EXPLAIN drops from 9.7s to ~2ms; end-to-end API latency 904–2891ms → 113–125ms.
- `/api/dictionary/search/grouped` `total` no longer silently caps at 200. When phase-1 hits the cap, a scoped `count(*)` reports the real number (e.g. `q=佛` now reports 2186 instead of 200). Adds one ~10ms count query only when the cap is hit; common-case rare queries pay nothing.

### Performance
- `/api/dictionary/sources` cached in Redis (10 min TTL). The full-table `GROUP BY source_id COUNT(*)` (~450ms cold on 360k rows) now runs at most once per 10 min; warm hits return in ~10ms server-side. Public `Cache-Control: max-age=300, stale-while-revalidate=600` lets CDNs and browsers further amortize.
- `/api/dictionary/hot` gets the same `Cache-Control` header (response is a constant list).

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
