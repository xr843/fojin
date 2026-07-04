"""Hot-question suggestions for the chat welcome screen and Tab cycling.

Extracted verbatim from ``app.services.chat`` (P1-3 god-file split) — see
that module for the orchestration that consumes ``get_hot_question_prompt``.
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hot_question import HotQuestion

logger = logging.getLogger(__name__)

DEFAULT_HOT_QUESTIONS = [
    "《心经》中「色不异空」的含义是什么？",
    "鸠摩罗什与玄奘的翻译风格有何不同？",
    "四圣谛的核心教义是什么？",
    "禅宗的「不立文字」思想源自哪些经典？",
]

HOT_QUESTION_CATEGORIES = ["白话翻译", "经文解读", "对比辨析", "佛教史话"]


async def get_hot_questions(db: AsyncSession, redis=None) -> list[str]:
    """Legacy string-list endpoint — used by the Tab-cycling suggestion fallback.

    Returns up to 8 display_text strings drawn from the active hot_questions
    table, spreading across all categories so the Tab suggestions feel varied.
    Falls back to DEFAULT_HOT_QUESTIONS if the table is empty.
    """
    stmt = (
        select(HotQuestion.display_text, HotQuestion.category)
        .where(HotQuestion.is_active.is_(True))
        .order_by(func.random())
        .limit(24)
    )
    rows = (await db.execute(stmt)).all()
    per_category: dict[str, list[str]] = {}
    for display_text, category in rows:
        per_category.setdefault(category, []).append(display_text)

    # Round-robin across categories so all four are represented
    questions: list[str] = []
    while len(questions) < 8 and per_category:
        for cat in list(per_category.keys()):
            if not per_category[cat]:
                del per_category[cat]
                continue
            questions.append(per_category[cat].pop(0))
            if len(questions) >= 8:
                break

    if not questions:
        questions = list(DEFAULT_HOT_QUESTIONS)
    return questions[:8]


async def get_random_hot_questions(
    db: AsyncSession,
    exclude_ids: list[int] | None = None,
) -> list[dict]:
    """Return one random active question per category for the welcome cards.

    Never exposes prompt_template to the frontend — only the id needed to
    echo back on click, the category label, and the display_text shown on
    the card. When exclude_ids is provided, each per-category pick first
    tries to avoid those ids; it only falls back to them if a category has
    no other active questions left.
    """
    exclude_set = set(exclude_ids or [])
    results: list[dict] = []
    for category in HOT_QUESTION_CATEGORIES:
        stmt = (
            select(HotQuestion.id, HotQuestion.category, HotQuestion.display_text)
            .where(
                HotQuestion.is_active.is_(True),
                HotQuestion.category == category,
            )
        )
        if exclude_set:
            stmt = stmt.where(~HotQuestion.id.in_(exclude_set))
        stmt = stmt.order_by(func.random()).limit(1)

        row = (await db.execute(stmt)).first()
        if row is None and exclude_set:
            # Category exhausted under the exclusion — relax and re-pick.
            stmt = (
                select(HotQuestion.id, HotQuestion.category, HotQuestion.display_text)
                .where(
                    HotQuestion.is_active.is_(True),
                    HotQuestion.category == category,
                )
                .order_by(func.random())
                .limit(1)
            )
            row = (await db.execute(stmt)).first()
        if row is None:
            continue
        results.append(
            {
                "id": row.id,
                "category": row.category,
                "display_text": row.display_text,
            }
        )
    return results


async def get_hot_question_prompt(
    db: AsyncSession, hot_question_id: int
) -> tuple[str, str] | None:
    """Fetch (display_text, prompt_template) for the given hot question id.

    Returns None if the id is unknown or inactive — the caller should then
    fall back to treating the user's message as-is.
    """
    row = (
        await db.execute(
            select(HotQuestion.display_text, HotQuestion.prompt_template).where(
                HotQuestion.id == hot_question_id,
                HotQuestion.is_active.is_(True),
            )
        )
    ).first()
    if row is None:
        return None
    return row.display_text, row.prompt_template


