"""Cross-canon alignment coverage — an ops view of the platform's moat.

`alignment_pairs` holds the LLM-verified chunk-level 汉↔藏/巴/梵 alignments that
are FoJin's flagship differentiator, but they're expensive to produce (each pair
is a 2-4h LLM-verification run costing real $). This aggregates, per lzh text
that has *any* alignment, how far along it is — distinct aligned juans vs the
text's total juans — so the operator can see which started-but-incomplete sutra
is the highest-ROI next batch instead of guessing.

Raw SQL over `alignment_pairs` (which has no ORM model — see api/alignment.py)
and `text_contents`, matching the catalog's Postgres-native style. The coverage
arithmetic + ranking is factored into `_shape_row` / `_sort_key` so it is
unit-tested without a Postgres fixture.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_COVERAGE_SQL = sql_text(
    """
    WITH lzh_pairs AS (
        SELECT text_a_id AS lzh_id, text_a_juan_num AS lzh_juan,
               text_b_lang AS other_lang, confidence
        FROM alignment_pairs
        WHERE text_a_lang = 'lzh' AND text_b_lang != 'lzh' AND text_b_id IS NOT NULL
        UNION ALL
        SELECT text_b_id, text_b_juan_num, text_a_lang, confidence
        FROM alignment_pairs
        WHERE text_b_lang = 'lzh' AND text_a_lang != 'lzh' AND text_a_id IS NOT NULL
    ),
    agg AS (
        SELECT lzh_id,
               count(*) AS pair_count,
               count(DISTINCT lzh_juan) AS aligned_juans,
               round(avg(confidence)::numeric, 2) AS avg_confidence,
               array_agg(DISTINCT other_lang ORDER BY other_lang) AS partner_langs
        FROM lzh_pairs
        GROUP BY lzh_id
    ),
    totals AS (
        SELECT text_id, count(DISTINCT juan_num) AS total_juans
        FROM text_contents
        WHERE lang = 'lzh'
        GROUP BY text_id
    )
    SELECT a.lzh_id, bt.title_zh, bt.dynasty,
           a.pair_count, a.aligned_juans,
           COALESCE(t.total_juans, 0) AS total_juans,
           a.avg_confidence, a.partner_langs
    FROM agg a
    JOIN buddhist_texts bt ON bt.id = a.lzh_id
    LEFT JOIN totals t ON t.text_id = a.lzh_id
    """
)


def _coverage_pct(aligned_juans: int, total_juans: int) -> float | None:
    """Aligned juans as a % of the text's total juans, rounded to 1 dp.

    None when total is unknown (0) — the text has alignment pairs but no lzh
    rows in text_contents, so a percentage would be meaningless (shown as '—').
    Capped at 100: an alignment can reference a juan beyond what text_contents
    knows about (stale import), which must not read as 137% covered.
    """
    if total_juans <= 0:
        return None
    return round(min(aligned_juans / total_juans * 100.0, 100.0), 1)


def _shape_row(row: Any) -> dict:
    """Turn one raw aggregate row into the API dict, computing coverage."""
    total = row.total_juans or 0
    aligned = row.aligned_juans or 0
    pct = _coverage_pct(aligned, total)
    return {
        "text_id": row.lzh_id,
        "title_zh": row.title_zh,
        "dynasty": row.dynasty,
        "pair_count": row.pair_count,
        "aligned_juans": aligned,
        "total_juans": total,
        "remaining_juans": max(total - aligned, 0) if total else None,
        "coverage_pct": pct,
        "avg_confidence": float(row.avg_confidence) if row.avg_confidence is not None else None,
        "partner_langs": list(row.partner_langs or []),
    }


def _sort_key(item: dict) -> tuple:
    """Rank biggest actionable gap first: most remaining juans on an already
    started pair, then most pairs (bigger/more-invested text). Unknown-total
    rows (remaining_juans None) sink to the bottom — can't act on them."""
    remaining = item["remaining_juans"]
    return (
        0 if remaining is not None else 1,        # known-total first
        -(remaining or 0),                         # biggest gap first
        -item["pair_count"],                       # then most invested
    )


async def compute_alignment_coverage(
    db: AsyncSession, *, limit: int = 200
) -> list[dict]:
    """Per-lzh-text cross-canon coverage, ranked by highest-ROI gap first."""
    rows = (await db.execute(_COVERAGE_SQL)).all()
    items = [_shape_row(r) for r in rows]
    items.sort(key=_sort_key)
    return items[:limit]
