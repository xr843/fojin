"""Turn real production failures into eval golden-set *candidates*.

The 90-question ``test_set.json`` is hand-curated and static; nothing feeds
live failures back into it, so the same mistake can regress forever without a
guard. This tool mines two failure signals already captured in prod —

  1. user thumbs-down (``chat_messages.feedback == 'down'``), and
  2. admin "bad" verdicts in the answer-quality review queue
     (``answer_reviews.verdict == 'bad'``, carrying a ``failure_category``) —

pairs each flagged answer with the user question that produced it (reusing
``answer_quality._attach_questions``, incl. its shared-timestamp ``<=`` edge
case), and emits **candidates** for a human to curate.

Why candidates, not auto-appended questions: a golden entry needs
``reference_sources`` / ``reference_answer_points`` — the *correct* answer's
provenance, which by definition a bad answer does not contain. The eval README
is emphatic that fossilising unverified gold sources silently guts the
regression gate (a title that doesn't fold-match ``buddhist_texts.title_zh``
scores a hidden 0 forever). So this tool surfaces the *questions worth adding*
and the *observed failure*, and leaves gold-source annotation to a human.

Usage::

    # Needs the prod corpus DB (chat_messages / answer_reviews live there).
    python -m eval.from_feedback --window-days 90 --limit 200
    # → eval/reports/feedback-candidates-<timestamp>.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.answer_review import AnswerReview
from app.models.chat import ChatMessage
from app.services.answer_quality import QueueItem, _attach_questions

logger = logging.getLogger(__name__)

EVAL_DIR = Path(__file__).resolve().parent
REPORTS_DIR = EVAL_DIR / "reports"

# First N chars of the flagged answer kept for the curator's context. Full
# answers can be long and are not needed to decide whether the question is
# worth a golden entry.
_ANSWER_EXCERPT_CHARS = 280


@dataclass
class FeedbackCandidate:
    """One question worth considering for the golden set, plus the failure
    evidence a curator needs. Everything under ``curate`` is for a human."""

    candidate_id: str
    question: str
    message_id: int
    signals: list[str]  # {"user_downvote", "admin_bad"}
    failure_category: str | None  # from AnswerReview, when admin-reviewed
    observed_answer_excerpt: str
    observed_sources: list[str]  # sutra titles the bad answer actually cited
    created_at: str
    # Placeholders a curator fills before promoting into test_set.json.
    curate: dict = field(
        default_factory=lambda: {
            "category": None,          # one of the 6 eval categories
            "reference_sources": [],   # title-level gold (verify against title_zh!)
            "reference_answer_points": [],
        }
    )


def _source_titles(sources) -> list[str]:
    """Best-effort extract sutra titles from a message's stored sources JSON."""
    if not isinstance(sources, list):
        return []
    titles: list[str] = []
    for s in sources:
        if isinstance(s, dict):
            title = s.get("title_zh") or s.get("title")
            if title:
                titles.append(title)
    # de-dupe, preserve order
    return list(dict.fromkeys(titles))


async def collect_feedback_candidates(
    db: AsyncSession, *, window_days: int = 90, limit: int = 200
) -> list[dict]:
    """Mine thumbs-down + admin-bad answers into curation candidates.

    Deterministic order: most recent first. A message flagged by BOTH signals
    is emitted once with both listed; the admin ``failure_category`` (if any)
    is always preferred over the bare downvote.
    """
    since = datetime.now(UTC) - timedelta(days=window_days)

    # 1) Admin "bad" verdicts, with their failure_category, inside the window.
    bad_reviews = (
        await db.execute(
            select(AnswerReview.message_id, AnswerReview.failure_category)
            .where(AnswerReview.verdict == "bad")
        )
    ).all()
    admin_category: dict[int, str | None] = {mid: cat for mid, cat in bad_reviews}

    # 2) The assistant messages themselves: any that were downvoted OR
    #    admin-flagged bad. One query, unioned by id.
    flagged_ids = set(admin_category)
    stmt = select(ChatMessage).where(
        ChatMessage.role == "assistant",
        ChatMessage.created_at >= since,
    )
    if flagged_ids:
        stmt = stmt.where(
            (ChatMessage.feedback == "down") | (ChatMessage.id.in_(flagged_ids))
        )
    else:
        stmt = stmt.where(ChatMessage.feedback == "down")
    rows = (
        await db.execute(stmt.order_by(ChatMessage.created_at.desc()))
    ).scalars().all()

    # Reuse the queue's battle-tested question pairing (shared-timestamp `<=`).
    queue_items = [
        QueueItem(
            message_id=m.id,
            session_id=m.session_id,
            answer=m.content,
            sources=m.sources,
            reason_tags=[],
            suspicion_score=0.0,
            feedback=m.feedback,
            created_at=m.created_at,
        )
        for m in rows
    ]
    await _attach_questions(db, queue_items)

    candidates: list[FeedbackCandidate] = []
    for m, item in zip(rows, queue_items, strict=True):
        signals: list[str] = []
        if m.feedback == "down":
            signals.append("user_downvote")
        if m.id in admin_category:
            signals.append("admin_bad")
        candidates.append(
            FeedbackCandidate(
                candidate_id=f"fb-{m.id}",
                question=item.question,
                message_id=m.id,
                signals=signals,
                failure_category=admin_category.get(m.id),
                observed_answer_excerpt=(m.content or "")[:_ANSWER_EXCERPT_CHARS],
                observed_sources=_source_titles(m.sources),
                created_at=m.created_at.isoformat() if m.created_at else "",
            )
        )
    return [asdict(c) for c in candidates[:limit]]


async def _amain(window_days: int, limit: int) -> None:
    from app.database import async_session

    async with async_session() as db:
        candidates = await collect_feedback_candidates(
            db, window_days=window_days, limit=limit
        )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    out = REPORTS_DIR / f"feedback-candidates-{ts}.json"
    payload = {
        "generated": datetime.now(UTC).isoformat(),
        "window_days": window_days,
        "count": len(candidates),
        "note": (
            "Curation candidates, NOT golden entries. Fill each 'curate' block "
            "(category + verified reference_sources) before adding to "
            "test_set.json. Verify sutra titles fold-match buddhist_texts.title_zh "
            "or the regression gate scores a hidden 0 — see eval/README.md."
        ),
        "candidates": candidates,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    n_down = sum(1 for c in candidates if "user_downvote" in c["signals"])
    n_admin = sum(1 for c in candidates if "admin_bad" in c["signals"])
    print(
        f"Wrote {len(candidates)} candidates → {out}\n"
        f"  user_downvote: {n_down}   admin_bad: {n_admin}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window-days", type=int, default=90)
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()
    asyncio.run(_amain(args.window_days, args.limit))


if __name__ == "__main__":
    main()
