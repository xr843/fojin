"""Export FoJin's cross-canon alignments as a publishable, license-stamped JSONL dataset.

FoJin's cross-canon alignments (Pāli–Classical Chinese, Classical Chinese–
Tibetan) are the project's most citable asset: parallel segments across
Buddhist canons barely exist in machine-readable form anywhere. This script
turns them into a flat, self-describing JSONL suitable for a public / HuggingFace
dataset release. The heavy lifting (SQL, record shapes, card aggregation) lives
in :mod:`app.services.alignment_export`, shared with the HTTP endpoint
``GET /exports/alignments.jsonl`` so the two never drift.

Output = a **dataset card** as the first JSONL line (or a companion ``--card``
file), then one JSON object per record.

Chunk granularity (default) record:
    {
      "id": 12345,
      "lang_src": "pi", "lang_tgt": "lzh",
      "src": {"text_id", "canonical_id", "title", "juan", "chunk_index",
              "license": {"spdx", "url"}, "attribution": "..."},
      "tgt": {...same...},
      "segment_src": "...", "segment_tgt": "...",
      "confidence": 0.92,
      "method": "embed_llm",
      "verified": false
    }

Sentence granularity (``--sentence``) record:
    {
      "id": 1, "align_type": "1-1", "similarity": 0.87, "method": "sentence-bertalign",
      "src": {"text_id", "title", "juan", "char_start", "char_end", "lang",
              "text", "license", "attribution"},
      "tgt": {...same...}
    }

Usage (run inside the backend container or with backend deps):
    python -m scripts.export_alignment_dataset --out /tmp/fojin_alignments.jsonl --version 1.0.0 --date 2026-07-11
    python -m scripts.export_alignment_dataset --sentence --out /tmp/fojin_sentences.jsonl
    python -m scripts.export_alignment_dataset --min-confidence 0.85 --langs pi-lzh,lzh-bo
    python -m scripts.export_alignment_dataset --methods manual,expert,flywheel-verified   # only reviewed rows
    python -m scripts.export_alignment_dataset --card /tmp/card.json --out /tmp/data.jsonl  # card in a side file
    python -m scripts.export_alignment_dataset --stats   # distribution only, no file

Notes:
    - Read-only: every statement is a SELECT; safe against production. (Do not
      run it against a live DB from here — validate with fixtures / the tests.)
    - Streaming: records are keyset-paginated, never fully buffered in memory.
    - ``--version`` / ``--date`` are passed in (not read from the wall clock); an
      omitted ``--date`` leaves ``generated_at`` off the card.
    - Segments are canonical-source text (CBETA / SuttaCentral / 84000 ingests);
      the alignment annotations are FoJin's and ship under CC BY-SA 4.0. Each
      record and the card carry per-source license metadata (see the dataset
      card, ``backend/docs/alignment-dataset-card.md``).
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.alignment_export import (
    build_card,
    collect_card_facts,
    compute_stats,
    iter_records,
)


def _split(value: str | None) -> list[str] | None:
    if not value:
        return None
    items = [v.strip() for v in value.split(",") if v.strip()]
    return items or None


async def run(args: argparse.Namespace) -> None:
    granularity = "sentence" if args.sentence else "chunk"
    langs = _split(args.langs)
    methods = _split(args.methods)

    if args.stats:
        stats = await compute_stats(
            granularity=granularity,
            min_confidence=args.min_confidence,
            langs=langs,
            methods=methods,
        )
        total = sum(s["count"] for s in stats)
        print(f"{granularity} records: {total}  min_score: {args.min_confidence}")
        for s in stats:
            key = s.get("langs") or s.get("align_type")
            avg = s["avg_score"]
            avg_str = f"{avg:.3f}" if avg is not None else "n/a"
            print(f"  {key}: {s['count']} records, avg {avg_str}")
        return

    record_count, source_licenses = await collect_card_facts(
        granularity=granularity,
        min_confidence=args.min_confidence,
        langs=langs,
        methods=methods,
    )
    card = build_card(
        granularity=granularity,
        version=args.version,
        generated_at=args.date,
        record_count=record_count,
        source_licenses=source_licenses,
    )

    out = Path(args.out)
    written = 0
    with out.open("w", encoding="utf-8") as f:
        if args.card:
            Path(args.card).write_text(
                json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        else:
            f.write(json.dumps(card, ensure_ascii=False) + "\n")
        async for rec in iter_records(
            granularity=granularity,
            min_confidence=args.min_confidence,
            langs=langs,
            methods=methods,
        ):
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            written += 1

    card_loc = f"card → {args.card}" if args.card else "card = line 1"
    print(
        f"wrote {out} ({out.stat().st_size / 1024:.0f} KB, {written} records, {card_loc}); "
        f"card record_count={record_count}, sources={len(source_licenses)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", default="/tmp/fojin_alignments.jsonl")
    parser.add_argument(
        "--sentence",
        action="store_true",
        help="export sentence_alignments (finer granularity) instead of chunk pairs",
    )
    parser.add_argument("--min-confidence", type=float, default=0.75, dest="min_confidence")
    parser.add_argument("--langs", help="comma-separated lang pairs, e.g. pi-lzh,lzh-bo")
    parser.add_argument(
        "--methods",
        help="comma-separated method filter, e.g. manual,expert,flywheel-verified "
        "(exclude unreviewed producers like embed_llm/embed_margin)",
    )
    parser.add_argument("--version", help="dataset version string for the card, e.g. 1.0.0")
    parser.add_argument(
        "--date",
        help="generated_at date for the card (e.g. 2026-07-11); omitted when absent",
    )
    parser.add_argument(
        "--card",
        help="write the dataset card to this JSON file instead of embedding it as line 1",
    )
    parser.add_argument("--stats", action="store_true", help="print distribution only, no file")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
