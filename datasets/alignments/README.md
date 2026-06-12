# FoJin Buddhist Canon Alignments (草案 / dataset card draft)

> 状态：**发布前草案**。发布到 HuggingFace 前需确认：dataset 名称（建议
> `fojin/buddhist-canon-alignments`）、license 最终选择、是否等 lzh-bo 批次扩充后再发 v0.1。
> 发布命令见文末。本文件即 HF dataset card（README.md）的底稿。

---

Chunk-level parallel segments across Buddhist canons: Pāli ↔ Classical
Chinese (Āgama/Nikāya parallels) and Classical Chinese ↔ Tibetan
(Kangyur parallels). Machine-aligned via embedding retrieval + LLM
verification, with per-pair confidence scores.

Parallel data across these canons barely exists in machine-readable,
segment-granular form. Existing resources (SuttaCentral parallels,
Bukkyō Dendō Kyōkai concordances) map at sutta/text level; this dataset
aligns at the passage level, making it usable for cross-lingual retrieval,
translation-pair mining, and computational philology.

## Current contents (v0.1 candidate, 2026-06-12)

| Direction | Pairs | Text pairs | Avg. confidence |
|---|---|---|---|
| Pāli → Classical Chinese (`pi-lzh`) | 3,095 | 211 | 0.892 |
| Classical Chinese → Tibetan (`lzh-bo`) | 955 | 5 | 0.902 |
| Classical Chinese → Pāli (`lzh-pi`) | 49 | 1 | 0.845 |
| **Total** | **4,099** | **236** | |

Sources: CBETA (Classical Chinese), SuttaCentral (Pāli), 84000 / Adarsha
(Tibetan), as ingested by [fojin.app](https://fojin.app).

## Record schema (JSONL, one object per line)

```json
{
  "id": 4144,
  "lang_src": "lzh", "lang_tgt": "bo",
  "src": {"text_id": 6, "canonical_id": "T0223", "title": "摩訶般若波羅蜜經",
           "juan": 1, "chunk_index": 4},
  "tgt": {"text_id": 5163, "canonical_id": "84K-toh9", "title": "Toh 9 (Kangyur)",
           "juan": 1, "chunk_index": 105},
  "segment_src": "…", "segment_tgt": "…",
  "confidence": 0.92,
  "method": "embed_llm",
  "verified": false
}
```

- `canonical_id` — CBETA Taishō number (`T…`/`X…`), SuttaCentral id (`SC-…`),
  or 84000 Tohoku number (`84K-toh…`)
- `confidence` — LLM verifier score at alignment time (pipeline threshold 0.75)
- `verified` — human-reviewed flag (currently false for all pairs; the
  alignment UI exists and verification is ongoing)

## Method

For each chunk of the source text: pgvector cosine top-20 candidates from
the target text → bilingual LLM verification (is-parallel + confidence) →
persist pairs ≥ 0.75. Pipeline:
[`backend/scripts/build_alignments.py`](https://github.com/xr843/fojin/blob/master/backend/scripts/build_alignments.py).
Export: [`backend/scripts/export_alignment_dataset.py`](https://github.com/xr843/fojin/blob/master/backend/scripts/export_alignment_dataset.py).

## Known limitations

- Machine-aligned; `verified: false` pairs have not been individually
  human-checked. Confidence scores come from the verifying LLM, not
  philological review.
- Chunking is retrieval-oriented (~embedding-window sized), so segment
  boundaries don't follow traditional textual divisions.
- `lzh-bo` currently covers only 5 texts (Lotus Sutra batch 1 + Prajñāpāramitā);
  expansion is ongoing.
- Source-text editions inherit any OCR/digitization issues from upstream.

## License

The underlying scriptures are public domain. The alignment annotations
(pairings, confidence, segmentation) are © FoJin contributors, released
under **CC BY-SA 4.0**.

## Citation

```bibtex
@misc{fojin-alignments-2026,
  title   = {FoJin Buddhist Canon Alignments: chunk-level Pāli–Chinese–Tibetan parallel segments},
  author  = {FoJin contributors},
  year    = {2026},
  url     = {https://fojin.app},
  note    = {Version 0.1}
}
```

---

## 发布操作（待确认后执行）

```bash
# 1. 导出最新数据（生产容器内，只读）
docker exec fojin-backend python -m scripts.export_alignment_dataset \
  --out /tmp/fojin_alignments.jsonl

# 2. 上传（需要 HF token，hf CLI）
hf upload fojin/buddhist-canon-alignments /tmp/fojin_alignments.jsonl data/alignments.jsonl --repo-type dataset
hf upload fojin/buddhist-canon-alignments datasets/alignments/README.md README.md --repo-type dataset
```

发布后回填：HF 链接进 fojin README + security-research 聚合页风格的引用入口。
