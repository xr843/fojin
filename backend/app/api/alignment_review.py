"""Admin review surface for the cross-canon alignment flywheel.

Lists mined candidates and lets an admin accept (→ promoted into the
ground-truth ``alignment_pairs``) or reject each. Mining itself (the pgvector
kNN batch) is a prod/cron operation via
``app.services.alignment_flywheel.mine_candidates`` — deliberately not an HTTP
endpoint, since it's long-running.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.role_guard import require_role
from app.database import get_db
from app.models.alignment_candidate import AlignmentCandidate
from app.models.text import BuddhistText
from app.services.alignment_flywheel import list_pending, review_candidate

router = APIRouter(prefix="/admin", tags=["admin"])


class AlignmentCandidateOut(BaseModel):
    id: int
    text_a_id: int
    text_a_title: str | None
    text_a_juan_num: int
    text_a_lang: str
    text_b_id: int
    text_b_title: str | None
    text_b_juan_num: int
    text_b_lang: str
    similarity: float
    source: str
    status: str


class ReviewRequest(BaseModel):
    accept: bool


async def _titles(db: AsyncSession, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = (await db.execute(
        select(BuddhistText.id, BuddhistText.title_zh).where(BuddhistText.id.in_(ids))
    )).all()
    return {r[0]: r[1] for r in rows}


def _to_out(c: AlignmentCandidate, titles: dict[int, str]) -> AlignmentCandidateOut:
    return AlignmentCandidateOut(
        id=c.id,
        text_a_id=c.text_a_id, text_a_title=titles.get(c.text_a_id),
        text_a_juan_num=c.text_a_juan_num, text_a_lang=c.text_a_lang,
        text_b_id=c.text_b_id, text_b_title=titles.get(c.text_b_id),
        text_b_juan_num=c.text_b_juan_num, text_b_lang=c.text_b_lang,
        similarity=c.similarity, source=c.source, status=c.status,
    )


@router.get("/alignment-candidates", response_model=list[AlignmentCandidateOut])
async def alignment_candidates(
    limit: int = Query(50, ge=1, le=200),
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Pending cross-canon alignment candidates, highest-similarity first."""
    pending = await list_pending(db, limit=limit)
    titles = await _titles(db, {c.text_a_id for c in pending} | {c.text_b_id for c in pending})
    return [_to_out(c, titles) for c in pending]


@router.post("/alignment-candidates/{candidate_id}/review", response_model=AlignmentCandidateOut)
async def review(
    candidate_id: int,
    body: ReviewRequest,
    user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Accept (→ promote into alignment_pairs) or reject a candidate."""
    c = await review_candidate(db, candidate_id, accept=body.accept, user_id=getattr(user, "id", None))
    if c is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    await db.commit()
    await db.refresh(c)
    titles = await _titles(db, {c.text_a_id, c.text_b_id})
    return _to_out(c, titles)
