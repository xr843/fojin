# Changelog

All notable changes to FoJin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added (2026-07-05)
- **Feedback → eval loop (`eval/from_feedback.py`)** — nothing fed live failures back into the 90-question golden set, so the same mistake could regress forever undetected. This tool mines two already-captured signals — user thumbs-down (`chat_messages.feedback == 'down'`) and admin "bad" verdicts (`answer_reviews.verdict == 'bad'`, with `failure_category`) — pairs each flagged answer with the user question that produced it (reusing `answer_quality._attach_questions`), and emits **curation candidates** (`eval/reports/feedback-candidates-*.json`). Deliberately not auto-appended to `test_set.json`: a golden entry needs the *correct* answer's `reference_sources`, which a bad answer can't provide, and the eval README is emphatic that unverified gold sources silently gut the regression gate. So real failures become candidate questions; gold-source annotation stays human. Loop documented in `eval/README.md`; unit-tested over in-memory SQLite (`tests/test_from_feedback.py`). This is the mechanism to grow the golden set 90→200+ from real usage rather than invented questions.

### Added (2026-07-04)
- **`/chat/stream` endpoint integration tests + chat-core coverage measurement** — the product's core path (HTTP endpoint → SSE generator → citation guard → persistence) was previously exercised pre-merge by nothing: existing stream tests call `send_message_stream` directly, so the endpoint layer (bearer-token parsing, `StreamingResponse` headers, actual wire bytes) had zero coverage. New `test_chat_stream_endpoint_integration.py` drives the real route through ASGI and locks the full SSE protocol (`padding → searching → session_id → token* → [citation_correction] → trust_status → sources → message_id → done`), the hallucinated-citation rewrite on the wire (event + corrected persistence + `fojin_citation_guard_mutations_total` increment), and the prep-rejection `error`+`done` path. Injection quirk documented in the test docstring: `sessionmaker=async_session` is a def-time default, so patching the module attr silently doesn't take — the seam is `functools.partial` at `app.api.chat`. CI now also measures (not gates) coverage for `chat` / `rag_retrieval` / `citation_guard`; baseline 56% / 47% / 96%.
- **Prometheus observability** — the backend now exposes `GET /metrics` (app root, deliberately NOT proxied by nginx → network-internal only; `METRICS_ENABLED=false` to disable). Per-handler HTTP request count/latency keyed by route *template* (bounded label cardinality; 404 scanner noise unrecorded), plus three chat-pipeline metrics: `fojin_rag_retrieval_seconds` (pgvector recall + rerank latency), `fojin_rag_context_chunks` (0-bucket spike = retrieval returning nothing), and `fojin_citation_guard_mutations_total` (anti-hallucination guard rewrites — previously only greppable as log lines). Opt-in scrape stack in `docker-compose.observability.yml` (Prometheus LTS, 127.0.0.1:9090, 256m cap); docs + PromQL alert candidates in `docs/OBSERVABILITY.md`. Notably NOT `prometheus-fastapi-instrumentator`: its `app.routes` walker assumes every route has `.path`, which FastAPI 0.139's internal `_IncludedRouter` nodes broke (116 test failures) — handler labels are derived from `request.scope` instead. Until now the only in-process production signals were `docker logs` text lines; the external smoke workflow catches downtime but says nothing about p95, retrieval quality drift, or citation-guard activity.

### Added (2026-06-11)
- **25,000-verse Prajñāpāramitā cross-canon alignment (Batch 2a, in flight)** — T0223《摩訶般若波羅蜜經》罗什译 ↔ 84000 Toh 9 Pañcaviṃśatisāhasrikā, the largest pair so far (815 lzh chunks × 12,022 bo chunks). Runs as four `--juans` slices (1-7 / 8-14 / 15-21 / 22-27); slice 1 landed 256 pairs at $2.32 (6.2% accept). The new `--juans` flag (#684) slices a huge pair into 2-4h sessions, each shipping queryable coverage immediately; pair definition in #685.
- **Cross-canon alignment catalog** (#693) — `GET /api/alignment/catalog` aggregates `alignment_pairs` lzh-side-normalized (10 texts, 3,800+ pairs and growing), and `/collections` gains a 「跨藏对照」 section: per-text chips with language tag + pair count, deep-linking into the reader at the juan with the most alignment anchors. Until this, the platform's flagship differentiator was only reachable from inside a reader the user had already opened.
- **Reading resume** (#690) — the reader records (juan, scroll position) per text in localStorage (throttled, scroller-aware — works whether the document or the `.reader-container` scrolls); returning visitors are restored to where they left off, the text detail page's primary button becomes 「继续阅读 · 第N卷」, and the homepage shows a 「继续阅读」 chip row. Also fixed the pre-existing `highlight_chunk` deep-link scrolling the wrong element when the AI panel is open.
- **Guest chat conversion hint** (#691) — after a guest's first successful AI answer, a dismissible notice explains the conversation won't be saved and offers sign-in. The CTA stashes the transcript in sessionStorage, the login page honors a `returnTo`, and the chat page restores the conversation after the round-trip — clicking "sign in to save" no longer destroys the very conversation it offers to save. 14-day dismissal memory.
- **学术动态 feed source audit** (#688) — 5 of 9 RSS sources had produced zero rows (404s, IP-blocked, frozen archives); replaced with 2 VPS-verified academic sources (Journal of Buddhist Ethics, SuttaCentral Discourse). The /activity page itself stays unlisted in the nav for now (#689).

### Fixed (2026-06-11)
- **SEO landing page CTAs were dead since launch** (#692) — all 10 `/sutras/*` pages navigated to `/texts/T0251/read`-style URLs, but the route takes the numeric `buddhist_texts.id`; `Number("T0251")` is NaN, the API 422s, and organic-search visitors hit a blank shell. `SutraInfo` now carries the prod-verified numeric `text_id`.
- **Stale service workers were never told to update** (#680, fixes #657) — the SW-refresh inline script added in #185 had been silently CSP-blocked since the security hardening (no `unsafe-inline`, no hash), so returning visitors could stay pinned to an old precached bundle indefinitely — presenting as "header buttons do nothing" in both Chrome and Safari for the reporter. The script now lives in an external file (CSP-allowed), a one-shot reload on `controllerchange` keeps page and precache in sync after deploys, and `/registerSW.js` is no-cache (Cloudflare had been edge-caching it for 4h).
- **PostgreSQL container cgroup OOM killed two alignment runs** — `mem_limit` raised 3g → 4g (chronic: same-pattern OOM storms on May 17-18, Jun 9, Jun 11; dmesg `oom-kill task=postgres` 90 seconds before each run death). Umami 256m → 384m (was at 88%).
- **Webhook auto-deploy was running a stale legacy `deploy.sh`** — `/home/admin/deploy.sh` (the path the GitHub-webhook CD service invokes) predated the #664 scripts/-filter (restarting backend on `backend/scripts/`-only merges, killing `docker exec` long-runs) and npm-built with `--no-cache` on every push (a memory/disk pressure source feeding the OOM above). Replaced with a thin wrapper exec-ing the repo-maintained script.

### Security
- Umami analytics tag is no longer hardcoded in `frontend/index.html`. The script is now injected at runtime by `frontend/src/umami.ts` only when both `VITE_UMAMI_URL` and `VITE_UMAMI_WEBSITE_ID` are set at build time (#623). Self-hosted deployments default to **no analytics phone-home** — previously every `docker compose up` silently reported search keywords, chat prompts (first 30 chars), reading IDs, and source clicks to `analytics.fojin.app`.
- Bumped `fastapi` 0.121.0 → 0.136.3, which transitively pulls `starlette` from 0.49.3 → 1.1.0 and closes PYSEC-2026-161 (Host-header URL-reconstruction inconsistency that could enable auth bypass when authentication compares against the reconstructed URL path). FoJin itself was not exploitable — `request.base_url` is only used in SEO sitemap/canonical generation, never in auth decisions — but the audit pipeline had been red for weeks. 334 backend tests pass under the new deps.

### Changed
- `deploy.sh` no longer exits early on "HEAD unchanged". It now also rebuilds frontend when `.env` is newer than the last build (since `VITE_*` envs are baked into the bundle as Dockerfile `ARG`s) and restarts backend when `.env` is newer than the last restart. Adds `--force-frontend` / `--force-backend` flags for manual overrides. Marker files live under `.deploy-state/` (gitignored, per-host). Fixes the silent "I changed .env but deploy says nothing to do" trap.
- `deploy.sh` now diffs against the marker commit, not `OLD_REV → NEW_REV`. Previously, if any other process (CD webhook, manual `git pull`) had already fast-forwarded the working tree, the script would see `Already up to date` and skip every service — silently leaving the new commit unbuilt. Markers now store the commit hash of the last successful build/restart, and per-service `git diff <marker> HEAD` decides what to do. `backend/requirements.txt` / `Dockerfile` / `pyproject.toml` changes now correctly upgrade `restart` → `rebuild image`, and a new `--rebuild-backend` flag exists for manual image rebuilds without a diff. Fixes the silent "CD pulled the commit but my deploy did nothing" trap.

### Added
- **8,000-verse Prajñāpāramitā cross-canon alignment (Batch 1.5, 2026-06-09)** — 127 chunk-level 汉藏 pairs landed for T0227《小品般若波羅蜜經》鳩摩羅什译 ↔ 84000 Toh 11 Aṣṭasāhasrikā Prajñāpāramitā. End-to-end DeepSeek API cost $3.64 (across two runs — see incident note below), all 127 pairs at confidence ≥ 0.75. Accept rate 3.4% (127 / 3,787 LLM-verified candidates), lower than Lotus's 8.6% because the sūtra's heavily repetitive paratactic style ("色不異空" / "is not other than emptiness") yields fewer 1:1 chunk-level correspondences than a narrative text. Total `alignment_pairs` grew from 3,429 → 3,556. Live at `/api/alignment/chunks/6482/...` and the reader's 「跨藏对照」 → 「按段对读」 panel at `/texts/6482/read`.
- **`deploy.sh` no longer restarts the backend container for changes confined to `backend/scripts/`, `backend/tests/`, `backend/eval/`, or `backend/alembic/`.** These directories hold CLI tools, pytest fixtures, the RAG eval harness, and migration files — none of them ride the live uvicorn process, so bouncing the container on those changes is pure noise. The change uncovered a concrete prod incident the prior day: merging PR #661 (a one-line addition to `backend/scripts/build_alignments.py`) caused the very next cron tick of `deploy.sh` to recreate the backend container, killing a `prajna_8k_zh_bo` alignment run that had been started 2.5h earlier via `docker exec`. `--commit-every 10` (from #659) protected the 82 already-committed pairs, but ~$1 of LLM verification work for the remaining chunks was lost and had to be re-paid on restart. If only the excluded directories changed, deploy.sh still bumps the backend marker so subsequent cron ticks don't re-log the same skip message every hour.
- **Lotus Sutra cross-canon alignment (Batch1, 2026-06-08)** — 259 chunk-level 汉藏 pairs landed for T0262《妙法蓮華經》罗什译 ↔ 84000 Toh 113 Saddharmapuṇḍarīka. End-to-end runtime 2h 45min, DeepSeek API cost $1.70 (vs $5 ceiling). All 259 pairs at confidence ≥ 0.80; 88% ≥ 0.95; 8.6% accept rate on 3,029 LLM-verified candidates. Total `alignment_pairs` grew from 3,170 → 3,429. First Mahayana 汉藏 pair to ship beyond the original 5 MVP, exposing the Lotus Sutra's cross-canon parallels in `/api/alignment/chunks/...` and the reader's 「跨藏对照」 → 「按段对读」 panel (verified live at `/texts/6513/read`, juan 3 藥草喻品 = 18/28 chunks aligned, 64% coverage).
- `build_alignments.py` un-archived from `backend/scripts/archive/misc/` back to `backend/scripts/` — the script is no longer a one-off; it now produces alignment_pairs incrementally as we add Mahayana 汉藏 pairs beyond the original 5 MVP keys. New `lotus_zh_bo` pair (T0262 妙法莲华经 罗什 ↔ 84000 Toh 113 Saddharmapuṇḍarīka) is Batch1's smoke test for the 汉藏 expansion: 182 lzh chunks × pgvector top-20 against 1307 bo chunks, $5 cost ceiling. Adds a `REASONING_MODELS_DENYLIST` (deepseek-v4-pro / deepseek-reasoner / o1*) — the script now refuses to start a real run when `settings.llm_model` falls back to a reasoning model (whose reasoning_tokens break `LLM_PRICE_PER_1K` cost estimates), unless `--force-reasoning-model` is passed. Operators should set `VERIFY_LLM_MODEL=deepseek-v4-flash` for batch verification.
- `build_alignments.py --commit-every N` (default 10) — checkpoint the open DB transaction after every N processed text_a chunks. The original commit-at-end-of-text_a behavior is fine for multi-text_a pairs (agama_*), but for single-text_a Mahayana pairs like `lotus_zh_bo` (182 chunks × ~20 candidates × ~4s LLM verify ≈ 2-3h) it left one transaction open the entire run. Each checkpoint also logs `✓accepted ✗llm ✗embed spent=$X` so live progress is visible from the log without staring at stderr or `tail -f`.
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
