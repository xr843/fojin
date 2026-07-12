# MITRA parallel data — license & attribution

Status: documentation only. Companion to the repo-root [`NOTICE`](../../NOTICE)
(MITRA section) and [`docs/mitra-alignment-integration.md`](../../docs/mitra-alignment-integration.md).

## Provenance

- **Dataset**: `dharmamitra/mitra-parallel` —
  [github.com/dharmamitra/mitra-parallel](https://github.com/dharmamitra/mitra-parallel)
- **Authors**: Sebastian Nehrdich & Kurt Keutzer (UC Berkeley),
  [arXiv:2601.06400](https://arxiv.org/abs/2601.06400)
- **License**: **CC BY-SA 4.0** (attribution + share-alike)
- **What we ingest**: sentence-level Sanskrit/Tibetan ↔ Buddhist-Chinese
  parallel pairs, imported into the `mitra_alignments` table by
  `backend/scripts/import_mitra_alignments.py`. Provenance is kept **per row**
  (`source='mitra-parallel'`, `license='CC-BY-SA-4.0'`) so this data stays
  attributable and license-separable from FoJin's own `alignment_pairs`.
- **Quality scores**: `mitra_alignments.mitra_e_score` (migration 0169) is
  backfilled by `backend/scripts/backfill_mitra_scores.py`. The current values
  are a FoJin-computed BGE-M3 cosine proxy, i.e. a *derived annotation* of the
  MITRA rows — see the share-alike note below.

## ShareAlike obligation

CC BY-SA 4.0's ShareAlike clause means any **adapted material** we build from
the MITRA pairs — re-anchored alignments (our chunk localization), filtered
subsets, added quality scores, exported calibration samples — must, if
distributed, be shared under **CC BY-SA 4.0** (or a compatible license). In
practice for FoJin:

- Redistributing `mitra_alignments` rows (dumps, dataset exports, the
  `--export-calibration` JSONL) keeps CC BY-SA 4.0 and must credit
  "MITRA / Dharmamitra (Nehrdich & Keutzer), CC BY-SA 4.0, arXiv:2601.06400".
- Merely *displaying* pairs in the reader with attribution is unproblematic;
  it is redistribution of derived alignment datasets that triggers ShareAlike.
- FoJin's Apache-2.0 code license is unaffected — ShareAlike attaches to the
  data, not to the software that processes it (see `NOTICE`).

## Open legal question — CC BY-SA × CBETA non-commercial

Flagged in `docs/research/2026-06-30-peer-projects-borrow-research.md`
(the MITRA item, "ShareAlike 约束叠 CBETA NC/84000 许可天花板评估", and the
action item "正式确认 … MITRA ShareAlike 与 CBETA NC 叠加边界" — around
line 90–98): the Chinese side of every MITRA pair is CBETA text, and CBETA is
**CC BY-NC-SA 4.0** (non-commercial). A combined artifact that contains both
the MITRA alignment structure (BY-SA) and CBETA sentence text (BY-NC-SA)
cannot simply be relicensed either way:

- CC BY-SA 4.0 and CC BY-NC-SA 4.0 are **not compatible licenses** for
  adaptation purposes — BY-SA adaptations may not add the NC restriction, and
  NC-SA material may not have NC stripped.
- The likely-safe reading is that a redistributed FoJin alignment dataset is a
  *collection/combination*: MITRA-originated fields (segment ids, foreign
  text, alignment structure, scores) under CC BY-SA 4.0, CBETA-quoted
  `zh_text` under CC BY-NC-SA 4.0, with the NC term effectively capping
  commercial redistribution of the combined rows. **This reading has not been
  legally confirmed.**
- Until it is, treat combined exports as NC-capped and keep both attributions
  on any redistribution.

**Action item (unresolved)**: formally confirm the ShareAlike × CBETA-NC
stacking boundary (and the analogous 84000 CC BY-NC-ND ceiling) before any
public dataset release beyond the reader UI.

## TODO — UI attribution

- [x] Reader parallel panel shows a `MITRA · CC BY-SA 4.0` credit per pair
      (shipped with PR #734; `ParallelPair.source == "mitra-parallel"`).
- [ ] Cross-canon **catalog** page: add a MITRA/CC BY-SA 4.0 credit where
      mitra-sourced coverage is aggregated (`sources` includes `"mitra"`).
- [ ] Any **chat/RAG** surface that starts quoting `mitra_alignments.foreign_text`
      must carry the same attribution line.
- [ ] A site-level data-licenses page summarizing `NOTICE` for end users,
      including the MITRA entry.

(No UI changes are made in this phase; the unchecked boxes are follow-ups.)
