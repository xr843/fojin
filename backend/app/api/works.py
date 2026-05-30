"""Read-only FRBR Work API.

Exposes the Work spine that aggregates cross-language / cross-canon witnesses
(BuddhistText rows) under an abstract work identity. All endpoints are
read-only — no INSERT / UPDATE / DELETE.

只读：作品详情、见证本列表、作品分页检索。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.text import BuddhistText
from app.models.work import Work, WorkWitness
from app.schemas.work import (
    WorkDetailResponse,
    WorkListItem,
    WorkListResponse,
    WorkWitnessResponse,
)

router = APIRouter(prefix="/works", tags=["works"])


def _work_not_found(slug: str) -> NotFoundError:
    """Build a 404 for a missing work.

    Uses the base ``NotFoundError`` (registered → 404 in the global
    ``STATUS_MAP``) rather than a new subclass, so no edits to the exception
    module / status map are needed.
    """
    return NotFoundError(f"作品未找到: {slug}")


# Per-witness-lang preference for the enriched witness title. The witness's own
# lang wins; otherwise fall back to title_en, then title_zh.
_LANG_TITLE_ATTR: dict[str, str] = {
    "lzh": "title_zh",
    "zh": "title_zh",
    "pi": "title_pi",
    "pli": "title_pi",
    "bo": "title_bo",
    "sa": "title_sa",
}


def _witness_title(text: BuddhistText, lang: str) -> str | None:
    """Pick the best available title for a witness given its language.

    Prefer the title matching the witness lang (title_zh for lzh, title_pi for
    pi, title_bo for bo, title_sa for sa); else fall back to title_en, then
    title_zh.
    """
    attr = _LANG_TITLE_ATTR.get(lang)
    if attr:
        val = getattr(text, attr, None)
        if val:
            return val
    return text.title_en or text.title_zh


@router.get("", response_model=WorkListResponse)
async def list_works(
    q: str | None = Query(None, description="标题模糊匹配 (title_primary / title_sa)"),
    lang: str | None = Query(None, description="按见证本语言过滤，如 lzh、pi、sa"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> WorkListResponse:
    """Paginated list of works.

    ``q`` does an ILIKE on title_primary / title_sa; ``lang`` keeps only works
    that have at least one witness in that language. Witness counts and the set
    of covered languages are aggregated in a single follow-up query (no N+1).

    作品分页检索：q 模糊匹配标题，lang 过滤含该语言见证本的作品。"""
    base = select(Work)

    if q:
        pattern = f"%{q}%"
        base = base.where(
            or_(
                Work.title_primary.ilike(pattern),
                Work.title_sa.ilike(pattern),
            )
        )

    if lang:
        base = base.where(
            Work.id.in_(
                select(WorkWitness.work_id).where(WorkWitness.lang == lang)
            )
        )

    # total count over the filtered set
    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar() or 0

    stmt = (
        base.order_by(Work.title_primary, Work.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    works = (await db.execute(stmt)).scalars().all()

    items: list[WorkListItem] = []
    work_ids = [w.id for w in works]
    if work_ids:
        # Single aggregate query for witness_count + covered langs across the page.
        agg_stmt = (
            select(
                WorkWitness.work_id,
                func.count(WorkWitness.id).label("witness_count"),
                func.array_agg(func.distinct(WorkWitness.lang)).label("langs"),
            )
            .where(WorkWitness.work_id.in_(work_ids))
            .group_by(WorkWitness.work_id)
        )
        agg = {
            row.work_id: (row.witness_count, row.langs)
            for row in (await db.execute(agg_stmt)).all()
        }
        for w in works:
            count, langs = agg.get(w.id, (0, []))
            items.append(
                WorkListItem(
                    slug=w.slug,
                    title_primary=w.title_primary,
                    title_sa=w.title_sa,
                    witness_count=count,
                    langs=sorted(lng for lng in (langs or []) if lng),
                )
            )

    return WorkListResponse(
        total=int(total), page=page, page_size=page_size, items=items
    )


@router.get("/{slug}", response_model=WorkDetailResponse)
async def get_work(slug: str, db: AsyncSession = Depends(get_db)) -> WorkDetailResponse:
    """Get a single work by slug, including its witness count.

    按 slug 获取作品详情（含见证本计数）。404 if slug not found."""
    work = (
        await db.execute(select(Work).where(Work.slug == slug))
    ).scalar_one_or_none()
    if work is None:
        raise _work_not_found(slug)

    witness_count = (
        await db.execute(
            select(func.count(WorkWitness.id)).where(WorkWitness.work_id == work.id)
        )
    ).scalar() or 0

    return WorkDetailResponse.model_validate(
        {
            "id": work.id,
            "slug": work.slug,
            "title_primary": work.title_primary,
            "title_sa": work.title_sa,
            "title_pi": work.title_pi,
            "sc_root_uid": work.sc_root_uid,
            "toh_number": work.toh_number,
            "category": work.category,
            "note": work.note,
            "created_at": work.created_at,
            "witness_count": int(witness_count),
        }
    )


@router.get("/{slug}/witnesses", response_model=list[WorkWitnessResponse])
async def list_work_witnesses(
    slug: str, db: AsyncSession = Depends(get_db)
) -> list[WorkWitnessResponse]:
    """List a work's witnesses, each enriched by joining BuddhistText.

    Order: role='root' first, then by lang asc, then text_id. The title is the
    best available for the witness language (see ``_witness_title``).

    列出作品的见证本（root 优先、再按语言、再按 text_id），并 join 经文表富化标题。
    404 if slug not found."""
    work = (
        await db.execute(select(Work.id).where(Work.slug == slug))
    ).scalar_one_or_none()
    if work is None:
        raise _work_not_found(slug)

    stmt = (
        select(WorkWitness, BuddhistText)
        .join(BuddhistText, BuddhistText.id == WorkWitness.text_id)
        .where(WorkWitness.work_id == work)
        .order_by(
            (WorkWitness.role != "root"),  # False (root) sorts before True
            WorkWitness.lang.asc(),
            WorkWitness.text_id.asc(),
        )
    )
    rows = (await db.execute(stmt)).all()

    return [
        WorkWitnessResponse(
            text_id=witness.text_id,
            cbeta_id=text.cbeta_id,
            title=_witness_title(text, witness.lang),
            lang=witness.lang,
            canon=witness.canon,
            role=witness.role,
            confidence=witness.confidence,
            has_content=bool(text.has_content),
        )
        for witness, text in rows
    ]
