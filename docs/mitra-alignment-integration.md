# MITRA Cross-Lingual Alignment Integration

Integration of the **MITRA-parallel** corpus (Sanskrit/Tibetan ↔ Buddhist-Chinese
sentence alignments) into FoJin's reader "多语对读" (cross-canon parallel) panel.

- **Source**: [github.com/dharmamitra/mitra-parallel](https://github.com/dharmamitra/mitra-parallel)
  — Nehrdich & Keutzer, [arXiv:2601.06400](https://arxiv.org/abs/2601.06400)
- **License**: CC BY-SA 4.0 (attribution, share-alike) — see `NOTICE`
- **Shipped**: 2026-06-14 (PRs #732, #734) + full-corpus data load
- **Scale**: **905,158** sentence pairs across **1,018** Taishō texts
  (Tibetan 675,356 / Sanskrit 229,802)

## Why a separate table (`mitra_alignments`, not `alignment_pairs`)

`alignment_pairs` is a **fojin-chunk ↔ fojin-chunk** model: the reader API
resolves the counterpart side by looking up `text_embeddings.chunk_text`. MITRA's
foreign side is an **inline** Sanskrit/Tibetan sentence that has no corresponding
fojin chunk (we do not ingest the Skt/Tib source texts as chunks), so it cannot
be expressed in `alignment_pairs`.

`mitra_alignments` stores the foreign text inline and anchors **only the Chinese
side** to a fojin chunk `(text_id, juan_num, chunk_index)`, located by verbatim
substring match of the MITRA Chinese sentence inside the juan. Per-row
`source`/`license` keeps the CC BY-SA 4.0 data attributable and license-separable.

## How it works

1. **Join key** — MITRA's Chinese segment ids are Taishō line refs
   (`T04n0192_002:0010c23_13`). Normalised to FoJin's `buddhist_texts.taisho_id`
   (`T04n0192` → `T0192`).
2. **Localisation (quality gate)** — `scripts/import_mitra_alignments.py` loads a
   text's `text_embeddings` chunks, builds a per-juan normalised concatenation +
   chunk-offset index, and finds each MITRA Chinese sentence verbatim → the
   containing `chunk_index`. Only sentences that localise are imported
   (~88% corpus-wide; ~98% for the well-covered major sutras). The import query
   uses `ix_text_embeddings_text_id` (≈6 ms/text, index scan — not a seq scan),
   runs one dedicated NullPool connection, and is idempotent per text.
3. **API** — `api/alignment.py`'s chunk + juan endpoints merge MITRA parallels;
   `ParallelPair.source` is `"fojin"` (deep-linkable) or `"mitra-parallel"`
   (inline Skt/Tib, no deep-link). Capped at `MITRA_CHUNK_LIMIT=50`/chunk.
4. **Reader** — `ReaderParallelPanel` (按段对读 tab) renders MITRA parallels with a
   `MITRA` tag, the inline foreign text, and a `MITRA · CC BY-SA 4.0` credit.

## Schema (migration 0156)

`mitra_alignments`: `id, text_id (FK buddhist_texts), taisho_id, juan_num,
chunk_index, zh_text, foreign_lang ('sa'|'bo'), foreign_text, zh_segment,
foreign_segment, mitra_file, match_scope, confidence, source, license,
created_at`. Indexes: `(text_id, juan_num, chunk_index)`, `(taisho_id)`,
`(text_id)`.

## PRs

| PR | What |
|----|------|
| #732 | migration 0156 + importer + API merge + NOTICE |
| #734 | reader rendering for `source="mitra-parallel"` (badge, fix dead deep-link) |
| #735 | importer uses one dedicated held connection (not the pooled session) |
| #733 | **GIN trigram index on `text_contents.content`** (see incident below) |

## Production incident retrospective (2026-06-14)

Running the first full-corpus `--all` import exhausted the Postgres connection
pool (85 stuck queries, 98/100 connections, new connections refused).

- **Root cause (not the import itself)**: `api/seo_dict.py._fetch_reverse_index`
  runs `text_contents.content ILIKE '%headword%'`. The docstring claimed the
  column was trigram-indexed, but **no such index existed** — every call
  seq-scanned the 406 MB table (~60 s). Crawler traffic on `/seo` dict pages
  fired many concurrently; the import's I/O slowed them further and they piled up.
- **Contributing**: importer used the app's pooled session (re-checks-out a
  connection per commit); app pool `30+90=120` > Postgres `max_connections=100`
  (shared with umami).
- **Remediation**: restarted backend + `pg_terminate_backend` on the zombie
  queries (98→15 connections); the live site stayed 200 throughout.
- **Fixes**: #733 (GIN trigram index — `/seo/dict/般若` 60 s → 0.3 s, verified via
  `EXPLAIN`), #735 (single dedicated import connection). With both deployed, the
  full-corpus re-run (905 k pairs) completed in **179 s with zero incident**
  (connections ≤ 32, no slow queries, site 200 throughout).

## Verification (full-corpus load)

- chunk-linkage integrity: **0** broken anchors (all 905,158 rows resolve to a
  real `text_embeddings` chunk)
- FK integrity: **0** orphan `text_id`
- same-juan match: 98.2% (16,153 cross-juan fallback)
- public API spot-checks: T0279 華嚴 → Tibetan Buddhāvataṃsaka; T0223/T0220
  Prajñāpāramitā → Tibetan (Subhūti dialogue); T0475 維摩詰 → inline parallels

## Open follow-ups (not done)

- **app pool / `max_connections` mismatch** (30+90 > 100, shared with umami):
  lower the pool, raise `max_connections`, and/or add a `statement_timeout`.
- Route content search to ES (fojin-es already indexes `text_contents`).
- MITRA-E (9B) semantic gate to prune the ~12% non-localising / weak pairs
  (run offline on GPU; the model needs ~36 GB).
- `api/alignment.py` `get_juan_alignment` N+1 (one MITRA query per chunk) →
  batch per juan.

## Acceptance (frontend)

Open a text with MITRA coverage in the reader, click **跨藏对照** (top toolbar),
switch to the **按段对读** tab, expand a segment → MITRA-tagged Sanskrit/Tibetan
parallels appear inline. Good demo: 維摩詰所說經 `/texts/28/read?juan=1`.
Raw API: `/api/alignment/chunks/28/1/<chunk_index>`.
