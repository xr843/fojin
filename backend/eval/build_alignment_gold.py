"""Build alignment gold-set *candidates* for the cross-canon quality eval.

The alignment stores only contain rows the pipeline *accepted*
(scripts/build_alignments.py counts rejections in a stats dict but never
persists them), so a gold set cannot be sampled from the DB alone — it would
have no negatives and precision would be unmeasurable. This tool emits:

  positives   — stratified samples from alignment_pairs / mitra_alignments /
                text_relations, ``label_source: "seed_verified"`` unless the
                row carries a human-verified flag,
  negatives   — *constructed* hard negatives:
                  shifted     same text pair, chunk_index offset ±1/±2 from a
                              known positive (adjacent chunks often continue
                              the same passage — the hardest kind, and some
                              may turn out to be true parallels on review),
                  cross_text  a chunk from an unrelated text (easy negative;
                              anchors the bottom of the calibration table),
                  near_neighbor  TODO — same-text high-cosine non-parallel
                              chunks need the embedding API to mine; reserved
                              in the format, not generated here.

Everything ``seed_verified`` (positives AND constructed negatives) still needs
human confirmation before the file is promoted to the final gold set — see
eval/ALIGNMENT_EVAL.md. Output is shuffled JSONL ready for that review pass.

Usage::

    # From a dataset export (no DB needed; format of
    # scripts/export_alignment_dataset.py):
    python -m eval.build_alignment_gold --from-export /tmp/fojin_alignments.jsonl

    # From the prod DB (positives from all three stores + generated negatives):
    python -m eval.build_alignment_gold --from-db --per-kind 50 --seed 42

Pure logic (record mapping, negative construction, stratified sampling) is
unit-tested in CI (tests/test_build_alignment_gold.py); the ``--from-db``
queries are thin and run only where the corpus DB is reachable.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from collections import Counter
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval.alignment_metrics import validate_gold_record

EVAL_DIR = Path(__file__).resolve().parent
REPORTS_DIR = EVAL_DIR / "reports"

SHIFT_OFFSETS = (-2, -1, 1, 2)

# Language-code → pair_kind side. The stores are inconsistent (buddhist_texts
# uses lzh/pi/bo/sa/en; MITRA TSVs have seen tib/skt variants), so fold
# aliases here instead of trusting any one spelling.
_LANG_ALIASES = {
    "lzh": "zh", "zh": "zh", "zho": "zh",
    "pi": "pi", "pli": "pi",
    "bo": "bo", "tib": "bo",
    "sa": "sa", "san": "sa", "skt": "sa",
    "en": "en", "eng": "en",
}


def normalize_lang(lang: str | None) -> str | None:
    if not lang:
        return None
    return _LANG_ALIASES.get(lang.strip().lower())


def pair_kind_from_langs(lang_a: str | None, lang_b: str | None) -> str | None:
    """``("pi", "lzh") → "zh-pi"`` — direction-normalized, zh always first.

    Returns ``None`` for unmappable languages or pairs without a Chinese side
    (the eval format only covers zh-X pairs; the caller counts skips).
    """
    a, b = normalize_lang(lang_a), normalize_lang(lang_b)
    if a is None or b is None or "zh" not in (a, b) or a == b:
        return None
    other = b if a == "zh" else a
    return f"zh-{other}"


# ---------------------------------------------------------------------------
# Positives
# ---------------------------------------------------------------------------

def export_row_to_gold(row: dict) -> dict | None:
    """One scripts/export_alignment_dataset.py JSONL row → a gold record.

    Returns ``None`` when the language pair doesn't map onto a zh-X
    ``pair_kind``. A row the pipeline's human review flagged (``verified``)
    is labeled ``human``; everything else is ``seed_verified`` — accepted by
    the embed+LLM pipeline, still awaiting human confirmation.
    """
    pair_kind = pair_kind_from_langs(row.get("lang_src"), row.get("lang_tgt"))
    if pair_kind is None:
        return None
    src, tgt = row["src"], row["tgt"]
    return {
        "record_id": f"ap-{row['id']}",
        "source": "alignment_pairs",
        "source_row_id": row["id"],
        "granularity": "chunk",
        "pair_kind": pair_kind,
        "side_a": {
            "text_id": src["text_id"],
            "juan_num": src.get("juan"),
            "chunk_index": src.get("chunk_index"),
            "lang": normalize_lang(row.get("lang_src")),
            "text": row.get("segment_src"),
        },
        "side_b": {
            "text_id": tgt["text_id"],
            "juan_num": tgt.get("juan"),
            "chunk_index": tgt.get("chunk_index"),
            "lang": normalize_lang(row.get("lang_tgt")),
            "text": row.get("segment_tgt"),
        },
        "label": True,
        "label_source": "human" if row.get("verified") else "seed_verified",
        "negative_kind": None,
        "note": f"method={row.get('method')} confidence={row.get('confidence')}",
    }


def mitra_row_to_gold(row: dict) -> dict | None:
    """One mitra_alignments row (as a plain dict) → a gold record.

    The foreign side is inline text — MITRA's Skt/Tib sentences have no fojin
    chunk (see migration 0156) — so ``side_b`` carries ``text``+``lang`` only.
    """
    pair_kind = pair_kind_from_langs("lzh", row.get("foreign_lang"))
    if pair_kind is None:
        return None
    return {
        "record_id": f"ma-{row['id']}",
        "source": "mitra_alignments",
        "source_row_id": row["id"],
        "granularity": "chunk",
        "pair_kind": pair_kind,
        "side_a": {
            "text_id": row["text_id"],
            "juan_num": row.get("juan_num"),
            "chunk_index": row.get("chunk_index"),
            "lang": "zh",
            "text": row.get("zh_text"),
        },
        "side_b": {
            "text": row.get("foreign_text"),
            "lang": normalize_lang(row.get("foreign_lang")),
        },
        "label": True,
        "label_source": "seed_verified",  # confidence is a constant 1.0 import flag, not a judgment
        "negative_kind": None,
        "note": f"taisho={row.get('taisho_id')} match_scope={row.get('match_scope')}",
    }


def relation_row_to_gold(row: dict) -> dict | None:
    """One text_relations parallel (sutta-level) → a gold record."""
    pair_kind = pair_kind_from_langs(row.get("lang_a"), row.get("lang_b"))
    if pair_kind is None:
        return None
    return {
        "record_id": f"tr-{row['id']}",
        "source": "text_relations",
        "source_row_id": row["id"],
        "granularity": "sutta",
        "pair_kind": pair_kind,
        "side_a": {"text_id": row["text_a_id"], "lang": normalize_lang(row.get("lang_a"))},
        "side_b": {"text_id": row["text_b_id"], "lang": normalize_lang(row.get("lang_b"))},
        "label": True,
        "label_source": "seed_verified",
        "negative_kind": None,
        "note": f"relation_source={row.get('source') or ''}",
    }


# ---------------------------------------------------------------------------
# Constructed negatives (chunk granularity, derived from known positives)
# ---------------------------------------------------------------------------

def _chunk_key(side: dict) -> tuple:
    return (side.get("text_id"), side.get("juan_num"), side.get("chunk_index"))


def positive_pair_keys(positives: Iterable[dict]) -> set[tuple]:
    """Direction-insensitive ``(a_chunk, b_chunk)`` keys of known positives."""
    keys: set[tuple] = set()
    for p in positives:
        a, b = _chunk_key(p["side_a"]), _chunk_key(p["side_b"])
        keys.add((a, b))
        keys.add((b, a))
    return keys


def make_shifted_negatives(
    positives: list[dict],
    chunk_exists: Callable[[int, int | None, int | None], bool],
    rng: random.Random,
    known_pairs: set[tuple] | None = None,
    per_positive: int = 1,
    offsets: tuple[int, ...] = SHIFT_OFFSETS,
) -> list[dict]:
    """Hard negatives: side_b shifted ±1/±2 chunks from a known positive.

    Every candidate is checked against ``chunk_exists`` (the shifted chunk
    must actually exist in text_embeddings) and against ``known_pairs``
    (a shift landing on another true positive is not a negative — with
    MAX_PARALLEL_PER_CHUNK=3 in the build pipeline, adjacent chunks of the
    same pair are often themselves aligned). Offsets are tried in
    rng-shuffled order so ±1 doesn't dominate; ids are deterministic
    (``neg-shifted-<seed record>{+|-}<offset>``) for reproducible review.
    """
    known = known_pairs if known_pairs is not None else positive_pair_keys(positives)
    negatives: list[dict] = []
    for p in positives:
        if p["granularity"] != "chunk" or p["side_b"].get("chunk_index") is None:
            continue  # sutta-level / inline-text rows have no chunk to shift
        candidates = list(offsets)
        rng.shuffle(candidates)
        made = 0
        for offset in candidates:
            if made >= per_positive:
                break
            side_b = {**p["side_b"], "chunk_index": p["side_b"]["chunk_index"] + offset}
            if side_b["chunk_index"] < 0:
                continue
            if not chunk_exists(side_b["text_id"], side_b.get("juan_num"), side_b["chunk_index"]):
                continue
            if (_chunk_key(p["side_a"]), _chunk_key(side_b)) in known:
                continue
            sign = f"+{offset}" if offset > 0 else str(offset)
            negatives.append({
                "record_id": f"neg-shifted-{p['record_id']}{sign}",
                "source": p["source"],
                "source_row_id": None,
                "granularity": "chunk",
                "pair_kind": p["pair_kind"],
                "side_a": dict(p["side_a"]),
                "side_b": side_b,
                "label": False,
                "label_source": "seed_verified",
                "negative_kind": "shifted",
                "note": f"chunk_index shifted {sign} from positive {p['record_id']}",
            })
            made += 1
    return negatives


def make_cross_text_negatives(
    positives: list[dict],
    chunk_pool: list[dict],
    rng: random.Random,
    related_text_pairs: set[tuple[int, int]] | None = None,
    per_positive: int = 1,
) -> list[dict]:
    """Easy negatives: side_b replaced by a chunk from an *unrelated* text.

    ``chunk_pool`` rows are ``{text_id, juan_num, chunk_index, lang}`` (plus
    optional ``text``). A pool chunk qualifies when its language matches the
    positive's side_b (so the negative is a plausible candidate for the same
    pair_kind) and its text is neither side of the positive nor related to
    side_a's text via ``related_text_pairs`` (both alignment stores +
    text_relations, direction-insensitive — a "negative" drawn from a genuine
    parallel text would poison the gold set).
    """
    related = related_text_pairs or set()
    negatives: list[dict] = []
    for p in positives:
        if p["granularity"] != "chunk":
            continue
        a_text_id = p["side_a"].get("text_id")
        b_text_id = p["side_b"].get("text_id")
        b_lang = p["side_b"].get("lang")
        eligible = [
            c for c in chunk_pool
            if normalize_lang(c.get("lang")) == b_lang
            and c["text_id"] not in (a_text_id, b_text_id)
            and (a_text_id, c["text_id"]) not in related
            and (c["text_id"], a_text_id) not in related
        ]
        if not eligible:
            continue
        picks = rng.sample(eligible, min(per_positive, len(eligible)))
        for i, chunk in enumerate(picks, 1):
            negatives.append({
                "record_id": f"neg-crosstext-{p['record_id']}-{i}",
                "source": p["source"],
                "source_row_id": None,
                "granularity": "chunk",
                "pair_kind": p["pair_kind"],
                "side_a": dict(p["side_a"]),
                "side_b": {
                    "text_id": chunk["text_id"],
                    "juan_num": chunk.get("juan_num"),
                    "chunk_index": chunk.get("chunk_index"),
                    "lang": normalize_lang(chunk.get("lang")),
                    "text": chunk.get("text"),
                },
                "label": False,
                "label_source": "seed_verified",
                "negative_kind": "cross_text",
                "note": f"unrelated-text chunk paired against side_a of {p['record_id']}",
            })
    return negatives


# NOTE near_neighbor negatives (same text pair, high embedding cosine, judged
# non-parallel) are the third — and most valuable — hard-negative family, but
# mining them needs the embedding API to rank same-text candidates, which this
# offline builder deliberately doesn't call. Reserved in the format
# (negative_kind: "near_neighbor"); see the TODO in eval/ALIGNMENT_EVAL.md.


# ---------------------------------------------------------------------------
# Stratification
# ---------------------------------------------------------------------------

def stratified_sample(records: list[dict], per_kind: int | None, rng: random.Random) -> list[dict]:
    """At most ``per_kind`` records per pair_kind, rng-sampled, order-stable input.

    ``per_kind=None`` keeps everything. Sampling happens per kind so one huge
    store (mitra_alignments' 896K zh-sa/zh-bo rows) can't drown the ~3K
    curated pairs in the mix.
    """
    if per_kind is None:
        return list(records)
    by_kind: dict[str, list[dict]] = {}
    for r in records:
        by_kind.setdefault(r["pair_kind"], []).append(r)
    out: list[dict] = []
    for kind in sorted(by_kind):
        group = by_kind[kind]
        out.extend(group if len(group) <= per_kind else rng.sample(group, per_kind))
    return out


def assemble_gold(
    positives: list[dict],
    negatives: list[dict],
    rng: random.Random,
) -> list[dict]:
    """Validate, de-duplicate by record_id, and shuffle into review order."""
    seen: set[str] = set()
    out: list[dict] = []
    for record in [*positives, *negatives]:
        problems = validate_gold_record(record)
        if problems:
            raise ValueError(f"invalid gold record {record.get('record_id')!r}: {problems}")
        if record["record_id"] in seen:
            continue
        seen.add(record["record_id"])
        out.append(record)
    rng.shuffle(out)
    return out


def write_jsonl(records: list[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def summarize(records: list[dict]) -> str:
    kinds = Counter(r["pair_kind"] for r in records)
    labels = Counter("positive" if r["label"] else f"negative/{r['negative_kind']}" for r in records)
    sources = Counter(r["source"] for r in records)
    return (
        f"records: {len(records)}\n"
        f"  by pair_kind: {dict(kinds)}\n"
        f"  by label:     {dict(labels)}\n"
        f"  by source:    {dict(sources)}"
    )


# ---------------------------------------------------------------------------
# --from-export mode (no DB)
# ---------------------------------------------------------------------------

def build_from_export(export_path: Path, per_kind: int | None, seed: int) -> list[dict]:
    """Positives only — an export has no rejected candidates to negate against
    and no text_embeddings to construct shifted negatives from. Pair it with
    ``--from-db`` (or hand-authored negatives) before measuring precision."""
    rng = random.Random(seed)
    positives: list[dict] = []
    skipped = 0
    with export_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = export_row_to_gold(json.loads(line))
            if record is None:
                skipped += 1
                continue
            positives.append(record)
    if skipped:
        print(f"skipped {skipped} export rows with non zh-X language pairs")
    positives = stratified_sample(positives, per_kind, rng)
    return assemble_gold(positives, [], rng)


# ---------------------------------------------------------------------------
# --from-db mode (async SQLAlchemy; prod only — needs the corpus DB)
# ---------------------------------------------------------------------------

# Deterministic pseudo-random ordering: md5(id || seed) gives a stable,
# roughly uniform sample per seed without materializing 896K mitra ids in
# Python on a small VPS.
_SQL_ALIGNMENT_PAIRS = """
SELECT p.id, p.text_a_id, p.text_a_juan_num, p.text_a_chunk_index, p.text_a_lang,
       p.text_b_id, p.text_b_juan_num, p.text_b_chunk_index, p.text_b_lang,
       p.confidence, p.method, p.is_verified,
       ea.chunk_text AS segment_a, eb.chunk_text AS segment_b
FROM alignment_pairs p
LEFT JOIN text_embeddings ea
       ON ea.text_id = p.text_a_id AND ea.juan_num = p.text_a_juan_num
      AND ea.chunk_index = p.text_a_chunk_index
LEFT JOIN text_embeddings eb
       ON eb.text_id = p.text_b_id AND eb.juan_num = p.text_b_juan_num
      AND eb.chunk_index = p.text_b_chunk_index
WHERE p.text_a_chunk_index IS NOT NULL AND p.text_b_chunk_index IS NOT NULL
ORDER BY md5(p.id::text || :seed)
LIMIT :cap
"""

_SQL_ALL_PAIR_KEYS = """
SELECT text_a_id, text_a_juan_num, text_a_chunk_index,
       text_b_id, text_b_juan_num, text_b_chunk_index
FROM alignment_pairs
WHERE text_a_chunk_index IS NOT NULL AND text_b_chunk_index IS NOT NULL
"""

_SQL_MITRA = """
SELECT id, text_id, taisho_id, juan_num, chunk_index, zh_text,
       foreign_lang, foreign_text, match_scope
FROM mitra_alignments
WHERE chunk_index IS NOT NULL
ORDER BY md5(id::text || :seed)
LIMIT :cap
"""

_SQL_RELATIONS = """
SELECT r.id, r.text_a_id, r.text_b_id, r.source,
       ta.lang AS lang_a, tb.lang AS lang_b
FROM text_relations r
JOIN buddhist_texts ta ON ta.id = r.text_a_id
JOIN buddhist_texts tb ON tb.id = r.text_b_id
WHERE r.relation_type = 'parallel'
ORDER BY md5(r.id::text || :seed)
LIMIT :cap
"""

_SQL_RELATED_TEXT_PAIRS = """
SELECT DISTINCT text_a_id, text_b_id FROM alignment_pairs
    WHERE text_a_id IS NOT NULL AND text_b_id IS NOT NULL
UNION
SELECT DISTINCT text_a_id, text_b_id FROM text_relations
"""

_SQL_CHUNK_POOL = """
SELECT te.text_id, te.juan_num, te.chunk_index, bt.lang, te.chunk_text AS text
FROM text_embeddings te
JOIN buddhist_texts bt ON bt.id = te.text_id
WHERE bt.lang = ANY(:langs)
ORDER BY md5(te.text_id::text || '-' || te.juan_num::text || '-'
             || te.chunk_index::text || :seed)
LIMIT :cap
"""


async def _fetch_existing_chunks(session, candidates: set[tuple]) -> set[tuple]:
    """Which ``(text_id, juan_num, chunk_index)`` triples exist in text_embeddings."""
    from sqlalchemy import text as sql_text

    triples = [c for c in candidates if all(v is not None for v in c)]
    if not triples:
        return set()
    # Values are ints from our own rows — inlined VALUES keeps this a single
    # round-trip (same rationale as build_alignments' inlined IN lists).
    values = ", ".join(f"({t}, {j}, {c})" for t, j, c in triples)
    result = await session.execute(sql_text(
        "SELECT te.text_id, te.juan_num, te.chunk_index "
        "FROM text_embeddings te "
        f"JOIN (VALUES {values}) AS v(text_id, juan_num, chunk_index) "  # nosec B608 — ints only
        "ON v.text_id = te.text_id AND v.juan_num = te.juan_num "
        "AND v.chunk_index = te.chunk_index"
    ))
    return {tuple(row) for row in result.fetchall()}


async def build_from_db(
    per_kind: int | None,
    seed: int,
    shifted_per_positive: int,
    cross_per_positive: int,
) -> list[dict]:
    from sqlalchemy import text as sql_text

    from app.database import async_session

    rng = random.Random(seed)
    seed_str = str(seed)
    # Oversample before stratification so per-kind sampling has headroom even
    # when one kind dominates a store.
    cap = (per_kind or 200) * 20

    async with async_session() as session:
        pair_rows = (await session.execute(
            sql_text(_SQL_ALIGNMENT_PAIRS), {"seed": seed_str, "cap": cap}
        )).mappings().all()
        mitra_rows = (await session.execute(
            sql_text(_SQL_MITRA), {"seed": seed_str, "cap": cap}
        )).mappings().all()
        relation_rows = (await session.execute(
            sql_text(_SQL_RELATIONS), {"seed": seed_str, "cap": cap}
        )).mappings().all()

        candidates = [
            export_row_to_gold({
                "id": row["id"],
                "lang_src": row["text_a_lang"], "lang_tgt": row["text_b_lang"],
                "src": {"text_id": row["text_a_id"], "juan": row["text_a_juan_num"],
                        "chunk_index": row["text_a_chunk_index"]},
                "tgt": {"text_id": row["text_b_id"], "juan": row["text_b_juan_num"],
                        "chunk_index": row["text_b_chunk_index"]},
                "segment_src": row["segment_a"], "segment_tgt": row["segment_b"],
                "confidence": row["confidence"], "method": row["method"],
                "verified": row["is_verified"],
            })
            for row in pair_rows
        ]
        candidates += [mitra_row_to_gold(dict(row)) for row in mitra_rows]
        candidates += [relation_row_to_gold(dict(row)) for row in relation_rows]
        positives = [r for r in candidates if r is not None]
        if len(positives) < len(candidates):
            print(f"skipped {len(candidates) - len(positives)} rows with non zh-X language pairs")

        positives = stratified_sample(positives, per_kind, rng)

        # Negatives are derived from the chunk-addressable positives.
        chunk_positives = [
            p for p in positives
            if p["granularity"] == "chunk" and p["side_b"].get("chunk_index") is not None
        ]

        # Known-positive pair keys across the WHOLE store (not just the
        # sample) so a shifted candidate can't collide with an unsampled
        # positive. ~3K rows — cheap.
        known_pairs: set[tuple] = set()
        for row in (await session.execute(sql_text(_SQL_ALL_PAIR_KEYS))).fetchall():
            a, b = tuple(row[0:3]), tuple(row[3:6])
            known_pairs.add((a, b))
            known_pairs.add((b, a))

        shift_candidates = {
            (p["side_b"]["text_id"], p["side_b"].get("juan_num"),
             p["side_b"]["chunk_index"] + offset)
            for p in chunk_positives for offset in SHIFT_OFFSETS
        }
        existing = await _fetch_existing_chunks(session, shift_candidates)

        pool_langs = sorted({
            p["side_b"].get("lang") for p in chunk_positives if p["side_b"].get("lang")
        })
        # gold "zh"/"pi"… back to buddhist_texts spellings for the SQL filter.
        db_langs = [{"zh": "lzh"}.get(lang, lang) for lang in pool_langs]
        chunk_pool = [
            dict(row) for row in (await session.execute(
                sql_text(_SQL_CHUNK_POOL),
                {"langs": db_langs, "seed": seed_str, "cap": 2000},
            )).mappings().all()
        ] if db_langs else []

        related_pairs = {
            (row[0], row[1])
            for row in (await session.execute(sql_text(_SQL_RELATED_TEXT_PAIRS))).fetchall()
        }

    shifted = make_shifted_negatives(
        chunk_positives,
        chunk_exists=lambda t, j, c: (t, j, c) in existing,
        rng=rng,
        known_pairs=known_pairs,
        per_positive=shifted_per_positive,
    )
    cross = make_cross_text_negatives(
        chunk_positives, chunk_pool, rng,
        related_text_pairs=related_pairs,
        per_positive=cross_per_positive,
    )
    return assemble_gold(positives, [*shifted, *cross], rng)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build alignment gold-set candidates (JSONL)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--from-export", metavar="PATH",
                      help="JSONL from scripts/export_alignment_dataset.py (positives only, no DB)")
    mode.add_argument("--from-db", action="store_true",
                      help="Pull stratified positives from the three stores and construct "
                           "shifted/cross_text negatives (needs the corpus DB)")
    parser.add_argument("--per-kind", type=int, default=None,
                        help="Max positives per pair_kind (default: keep all)")
    parser.add_argument("--seed", type=int, default=42,
                        help="RNG seed — same seed, same sample/negatives/shuffle (default 42)")
    parser.add_argument("--shifted-per-positive", type=int, default=1,
                        help="Shifted hard negatives per chunk positive (default 1)")
    parser.add_argument("--cross-per-positive", type=int, default=1,
                        help="Cross-text negatives per chunk positive (default 1)")
    parser.add_argument("--out", type=str, default=None,
                        help="Output path (default eval/reports/alignment-gold-candidates-<ts>.jsonl)")
    args = parser.parse_args(argv)

    if args.from_export:
        records = build_from_export(Path(args.from_export), args.per_kind, args.seed)
    else:
        records = asyncio.run(build_from_db(
            args.per_kind, args.seed, args.shifted_per_positive, args.cross_per_positive,
        ))

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
    else:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        out = REPORTS_DIR / f"alignment-gold-candidates-{ts}.jsonl"
    write_jsonl(records, out)
    print(summarize(records))
    print(f"wrote {out}")
    print(
        "NOTE: these are CANDIDATES. Everything label_source=seed_verified "
        "(positives and constructed negatives) needs human confirmation before "
        "promotion to the gold set — see eval/ALIGNMENT_EVAL.md."
    )


if __name__ == "__main__":
    main()
