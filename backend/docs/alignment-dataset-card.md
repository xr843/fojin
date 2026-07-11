# FoJin Cross-Canon Alignment Dataset — Dataset Card

`dataset: fojin-cross-canon-alignments`

FoJin (佛津) publishes a versioned, license-clean export of its **cross-canon
alignment data**: parallel Buddhist-scripture segments across Classical Chinese,
Pāli, Sanskrit, and Tibetan, with per-pair provenance and per-source license
metadata. Machine-readable parallels of this kind barely exist anywhere; this
export turns FoJin's alignment data moat into a **citable public artifact**.

- **Dataset license (annotations)**: **CC BY-SA 4.0** — see [License](#license--sharealike).
- **Segment text**: quoted from upstream canonical sources under *their* own
  licenses (see [Per-source licenses](#per-source-licenses)).
- **Regenerate**: `scripts/export_alignment_dataset.py` or
  `GET /exports/alignments.jsonl` — see [Regenerating](#regenerating-the-dataset).

---

## What's in it

Two granularities, published as separate JSONL files:

| Granularity | Source table | One record = | Availability |
| --- | --- | --- | --- |
| `chunk` (default) | `alignment_pairs` (+ `text_embeddings` for segment text) | one aligned chunk pair, both segments inline | populated |
| `sentence` | `sentence_alignments` (migration 0170) | one aligned sentence pair (bertalign refinement) | empty until the prod refinement job runs; the export still emits a valid card with `record_count: 0` |

Each side of a pair links to a `buddhist_texts` row and, through it
(`buddhist_texts.source_id → data_sources`), to the license of the canon it was
ingested from.

## Format

Line-delimited JSON (**JSONL / NDJSON**, `application/x-ndjson`):

- **Line 1 is the dataset card** — the object below (has a `dataset` key).
- **Every subsequent line is one record** (has an `id` key).

The CLI can instead write the card to a companion file with `--card PATH`, in
which case line 1 of the JSONL is already the first record.

### Dataset card (line 1)

```json
{
  "dataset": "fojin-cross-canon-alignments",
  "version": "1.0.0",
  "generated_at": "2026-07-11",
  "record_count": 12345,
  "granularity": "chunk",
  "license": "CC-BY-SA-4.0",
  "source_licenses": [
    {"source": "CBETA", "spdx": "CC-BY-NC-SA-4.0", "url": "https://www.cbeta.org/copyright.php", "attribution_required": true},
    {"source": "SuttaCentral", "spdx": "CC0-1.0", "url": "https://suttacentral.net/licensing", "attribution_required": false}
  ],
  "provenance_note": "Alignment annotations … are FoJin's own contribution and are released under CC BY-SA 4.0. The quoted segment text belongs to the upstream canonical sources …",
  "citation": "FoJin (佛津) Cross-Canon Alignment Dataset v1.0.0. …"
}
```

- `generated_at` is caller-supplied (`--date`) and **omitted** when not provided
  (the runtime forbids wall-clock reads in some contexts, so the export never
  invents a timestamp).
- `source_licenses` is aggregated from the **distinct `data_sources` rows
  actually present in the exported records** (both sides), so the card
  truthfully reflects only the sources it includes.

### Chunk record

```json
{
  "id": 12345,
  "lang_src": "pi",
  "lang_tgt": "lzh",
  "src": {
    "text_id": 200, "canonical_id": "SC-mn10", "title": "Satipaṭṭhānasutta",
    "juan": 1, "chunk_index": 4,
    "license": {"spdx": "CC0-1.0", "url": "https://suttacentral.net/licensing"},
    "attribution": "SuttaCentral (CC0-1.0)"
  },
  "tgt": {
    "text_id": 300, "canonical_id": "T0026", "title": "中阿含經",
    "juan": 2, "chunk_index": 7,
    "license": {"spdx": "CC-BY-NC-SA-4.0", "url": "https://www.cbeta.org/copyright.php"},
    "attribution": "CBETA (CC-BY-NC-SA-4.0)"
  },
  "segment_src": "Evaṃ me sutaṃ …",
  "segment_tgt": "我聞如是 …",
  "confidence": 0.92,
  "method": "embed_llm",
  "verified": false
}
```

Field notes:

- `confidence` — the LLM/reviewer quality score at build time.
- `method` — the producing pipeline: `embed_llm` | `embed_margin` | `manual` |
  `expert` | `flywheel-verified`. Use `--methods` / `?methods=` to exclude
  unreviewed producers (e.g. keep only `manual,expert,flywheel-verified`).
- `verified` — human-verified flag.
- `license` / `attribution` are **per side** (each segment can be under a
  different license). `license` is `null` when the source is unaudited.
- **Backward compatibility**: every field emitted by the pre-license exporter is
  preserved unchanged; `license` and `attribution` are purely additive keys
  nested inside `src` / `tgt`.

### Sentence record

```json
{
  "id": 1,
  "align_type": "1-1",
  "similarity": 0.87,
  "method": "sentence-bertalign",
  "src": {
    "text_id": 200, "title": "Satipaṭṭhānasutta", "juan": 1,
    "char_start": 10, "char_end": 55, "lang": "pi", "text": "Evaṃ me sutaṃ",
    "license": {"spdx": "CC0-1.0", "url": "https://suttacentral.net/licensing"},
    "attribution": "SuttaCentral (CC0-1.0)"
  },
  "tgt": {
    "text_id": 300, "title": "中阿含經", "juan": 2,
    "char_start": 0, "char_end": 40, "lang": "lzh", "text": "我聞如是",
    "license": {"spdx": "CC-BY-NC-SA-4.0", "url": "https://www.cbeta.org/copyright.php"},
    "attribution": "CBETA (CC-BY-NC-SA-4.0)"
  }
}
```

- `align_type` — the bertalign move (`1-1` | `1-2` | `2-1`).
- `similarity` — averaged cross-lingual cosine; filtered by `min_confidence`.
- `char_start` / `char_end` — offsets into the `(text_id, juan, lang)`
  `text_contents.content` row (the re-chunking-stable anchor from migration
  0168), so a segment stays locatable across re-ingests.

## Per-source licenses

The segment text is **not** FoJin's to relicense; it keeps each upstream
canon's license. Representative sources (authoritative values live on
`data_sources`; see the repo-root [`NOTICE`](../../NOTICE)):

| Source | SPDX | Commercial | Notes |
| --- | --- | --- | --- |
| CBETA (中華電子佛典協會) | `CC-BY-NC-SA-4.0` | No | Commercial use needs separate CBETA authorization. Caps combined exports to non-commercial. |
| SuttaCentral | `CC0-1.0` (Pāli) / `CC-BY-SA` (translations) | Yes | Public-domain Pāli root texts. |
| 84000 | `CC-BY-NC-ND-4.0` | No | No-derivatives ceiling; treat as reference-only. |
| MITRA / Dharmamitra | `CC-BY-SA-4.0` | Yes (SA) | Sanskrit/Tibetan ↔ Chinese; see [`mitra-license.md`](mitra-license.md). |

The card's `source_licenses` reflects exactly the sources present in a given
export, so a subset export (e.g. `--langs pi-lzh`) carries only the relevant
licenses.

## License & ShareAlike

- **FoJin's alignment annotations** (the pairings, `confidence`/`similarity`,
  `method`, `verified` flag) are released under **CC BY-SA 4.0**. Any
  redistributed adaptation of these annotations must remain CC BY-SA 4.0 (or a
  compatible license) and credit FoJin — this is the ShareAlike obligation.
- **The quoted segment text** stays under its source's license (see the table).
  Redistribution must preserve **every** source's attribution and license terms.
- **NonCommercial ceiling**: when an export includes CBETA text
  (`CC-BY-NC-SA-4.0`) or 84000 text (`CC-BY-NC-ND-4.0`), the *combined* dataset
  is effectively **non-commercial** — CC BY-SA and CC BY-NC-SA are not
  compatible for adaptation, so the NC term of the included text caps commercial
  reuse of the combined rows. The safe reading treats a redistributed export as
  a *collection*: FoJin's BY-SA annotations + each source's own-licensed text.
  This stacking has **not been legally confirmed**; the full analysis (incl. the
  MITRA × CBETA-NC boundary) is in [`mitra-license.md`](mitra-license.md).
  **Do not publish a commercial-use export until that boundary is confirmed.**

## How to cite

> FoJin (佛津) Cross-Canon Alignment Dataset v{version}. FoJin Buddhist Digital
> Text Platform, https://fojin.org. Alignment annotations licensed CC BY-SA 4.0.

When redistributing records, also carry the attribution string of each included
source (e.g. `CBETA (CC-BY-NC-SA-4.0)`, `MITRA / Dharmamitra (Nehrdich &
Keutzer), CC BY-SA 4.0, arXiv:2601.06400`).

## Versioning policy

- The dataset is versioned with **SemVer** in the card's `version` field.
- **MAJOR** — a breaking schema change (renamed/removed record fields).
- **MINOR** — additive schema changes (new fields), or a materially larger
  corpus (new canons / language pairs).
- **PATCH** — data corrections and re-alignments with no schema change.
- `version` and `generated_at` are **passed in at export time** (`--version` /
  `--date`), never read from the wall clock, so the same DB state reproduces the
  same card. Tag each public release with its `version` + the source DB snapshot.

## Regenerating the dataset

**CLI** (inside the backend container / with backend deps; read-only, streaming):

```bash
# chunk pairs, card as line 1
python -m scripts.export_alignment_dataset \
    --out fojin_alignments.jsonl --version 1.0.0 --date 2026-07-11

# reviewed rows only, one language pair, higher threshold
python -m scripts.export_alignment_dataset \
    --methods manual,expert,flywheel-verified --langs pi-lzh --min-confidence 0.85 \
    --out fojin_alignments_reviewed.jsonl

# sentence granularity (empty until the prod job lands)
python -m scripts.export_alignment_dataset --sentence --out fojin_sentences.jsonl

# write the card to a side file instead of line 1
python -m scripts.export_alignment_dataset --card card.json --out data.jsonl

# distribution only, no file
python -m scripts.export_alignment_dataset --stats
```

**HTTP** (streaming; the card is always line 1):

```
GET /api/exports/alignments.jsonl?granularity=chunk|sentence&min_confidence=&methods=
```

Example:

```bash
curl 'https://fojin.org/api/exports/alignments.jsonl?granularity=chunk&methods=manual,expert' \
    -o fojin_alignments.jsonl
```

Both paths share `app/services/alignment_export.py`, so the SQL, the record
shapes, and the card aggregation are identical.
