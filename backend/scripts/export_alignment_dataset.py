"""Export verified cross-canon alignment pairs as a publishable JSONL dataset.

FoJin's chunk-level alignments (Pāli–Classical Chinese, Classical Chinese–
Tibetan) are the project's most citable asset: parallel segments across
Buddhist canons barely exist in machine-readable form anywhere. This script
turns the `alignment_pairs` table into a flat, self-describing JSONL suitable
for a HuggingFace dataset release (one record per pair, full provenance).

Output schema (one JSON object per line):
    {
      "id": 12345,                      # stable alignment_pairs.id
      "lang_src": "pi", "lang_tgt": "lzh",
      "src": {"text_id", "canonical_id", "title", "juan", "chunk_index"},
      "tgt": {...same...},
      "segment_src": "...", "segment_tgt": "...",
      "confidence": 0.92,               # LLM verifier confidence at build time
      "method": "embed_llm",            # alignment pipeline variant
      "verified": false                 # human-verified flag
    }

Usage (run inside the backend container or with backend deps):
    python -m scripts.export_alignment_dataset --out /tmp/fojin_alignments.jsonl
    python -m scripts.export_alignment_dataset --min-confidence 0.85 --langs pi-lzh
    python -m scripts.export_alignment_dataset --stats   # distribution only, no file

Notes:
    - Read-only: single SELECT, no writes, safe against production.
    - Segments are canonical-source text (CBETA / SuttaCentral / etc. ingests);
      the underlying scriptures are public domain. The alignment annotations
      are FoJin's and ship under CC BY-SA 4.0 (see dataset card).
"""

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import async_session

EXPORT_SQL = """
SELECT
    p.id,
    p.text_a_lang        AS lang_src,
    p.text_b_lang        AS lang_tgt,
    p.text_a_id,
    ta.cbeta_id          AS src_canonical_id,
    ta.title_zh          AS src_title,
    p.text_a_juan_num    AS src_juan,
    p.text_a_chunk_index AS src_chunk,
    p.text_b_id,
    tb.cbeta_id          AS tgt_canonical_id,
    tb.title_zh          AS tgt_title,
    p.text_b_juan_num    AS tgt_juan,
    p.text_b_chunk_index AS tgt_chunk,
    ea.chunk_text        AS segment_src,
    eb.chunk_text        AS segment_tgt,
    p.confidence,
    p.method,
    p.is_verified
FROM alignment_pairs p
JOIN buddhist_texts ta ON ta.id = p.text_a_id
JOIN buddhist_texts tb ON tb.id = p.text_b_id
-- alignment_pairs stores chunk references; the segment text lives in
-- text_embeddings (chunk_text), addressed by (text_id, juan_num, chunk_index)
JOIN text_embeddings ea
  ON ea.text_id = p.text_a_id
 AND ea.juan_num = p.text_a_juan_num
 AND ea.chunk_index = p.text_a_chunk_index
JOIN text_embeddings eb
  ON eb.text_id = p.text_b_id
 AND eb.juan_num = p.text_b_juan_num
 AND eb.chunk_index = p.text_b_chunk_index
WHERE p.confidence >= :min_confidence
ORDER BY p.text_a_id, p.text_a_juan_num, p.text_a_chunk_index, p.id
"""


def to_record(row) -> dict:
    return {
        "id": row.id,
        "lang_src": row.lang_src,
        "lang_tgt": row.lang_tgt,
        "src": {
            "text_id": row.text_a_id,
            "canonical_id": row.src_canonical_id,
            "title": row.src_title,
            "juan": row.src_juan,
            "chunk_index": row.src_chunk,
        },
        "tgt": {
            "text_id": row.text_b_id,
            "canonical_id": row.tgt_canonical_id,
            "title": row.tgt_title,
            "juan": row.tgt_juan,
            "chunk_index": row.tgt_chunk,
        },
        "segment_src": row.segment_src,
        "segment_tgt": row.segment_tgt,
        "confidence": row.confidence,
        "method": row.method,
        "verified": row.is_verified,
    }


async def run(args: argparse.Namespace) -> None:
    wanted_langs = set(args.langs.split(",")) if args.langs else None

    async with async_session() as session:
        result = await session.execute(
            text(EXPORT_SQL), {"min_confidence": args.min_confidence}
        )
        rows = result.fetchall()

    records = [
        to_record(r)
        for r in rows
        if wanted_langs is None or f"{r.lang_src}-{r.lang_tgt}" in wanted_langs
    ]

    dist = Counter(f"{r['lang_src']}-{r['lang_tgt']}" for r in records)
    texts = len({(r["src"]["text_id"], r["tgt"]["text_id"]) for r in records})
    print(f"pairs: {len(records)}  text-pairs: {texts}  min_conf: {args.min_confidence}")
    for langs, n in dist.most_common():
        confs = [r["confidence"] for r in records if f"{r['lang_src']}-{r['lang_tgt']}" == langs]
        print(f"  {langs}: {n} pairs, avg conf {sum(confs) / len(confs):.3f}")

    if args.stats:
        return

    out = Path(args.out)
    with out.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", default="/tmp/fojin_alignments.jsonl")
    parser.add_argument("--min-confidence", type=float, default=0.75)
    parser.add_argument("--langs", help="comma-separated lang pairs, e.g. pi-lzh,lzh-bo")
    parser.add_argument("--stats", action="store_true", help="print distribution only")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
