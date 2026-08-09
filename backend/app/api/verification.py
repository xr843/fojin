"""Public quote-verification endpoint — the AI-facing half of fojin's
"每一句都能点回原典" contract.

GET /api/verify/quote?q=…&cite=…&juan=…

Any agent that has written a Buddhist-canon quote can ask, in one call,
whether that quote exists verbatim in the corpus (and where), instead of
serving its readers an invented citation. Read-only; strict-rate-limited
(paid nothing, but ES + source-text reads are not free).
"""

from elasticsearch import AsyncElasticsearch
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.elasticsearch import get_es
from app.database import get_db
from app.schemas.verification import QuoteVerdict
from app.services.quote_lookup import QuoteTooShortError, verify_quote

router = APIRouter(prefix="/verify", tags=["verification"])


@router.get("/quote", response_model=QuoteVerdict)
async def verify_quote_endpoint(
    q: str = Query(..., min_length=1, max_length=400, description="待核验的引文"),
    cite: str | None = Query(
        None,
        max_length=120,
        description="出处提示：CBETA 编号(T0374)或 fojin URN(fojin:cbeta/T0374.13)",
    ),
    juan: int | None = Query(None, ge=1, le=999, description="卷号提示"),
    db: AsyncSession = Depends(get_db),
) -> QuoteVerdict:
    """逐字引文核验（开放世界）。

    Verify a quote verbatim against the whole corpus. Returns where it was
    found (URN-cited), or the closest near-miss window when it wasn't.
    Rate limit: strict (see rate_limit_verify_quote)."""
    es: AsyncElasticsearch = get_es()
    try:
        return await verify_quote(db, es, q, cite=cite, juan=juan)
    except QuoteTooShortError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
