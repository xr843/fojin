"""Public quote-verification endpoint — the AI-facing half of fojin's
"每一句都能点回原典" contract.

GET /api/verify/quote?q=…&cite=…&juan=…

Any agent that has written a Buddhist-canon quote can ask, in one call,
whether that quote exists verbatim in the corpus (and where), instead of
serving its readers an invented citation. Read-only; strict-rate-limited
(paid nothing, but ES + source-text reads are not free).
"""

from typing import Annotated

from elasticsearch import AsyncElasticsearch
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.elasticsearch import get_es
from app.database import get_db
from app.schemas.verification import ClaimVerdict, QuoteVerdict
from app.services.claim_check import check_claim, credit_runs
from app.services.quote_lookup import (
    MIN_LOOKUP_QUOTE_CHARS,
    QuoteTooShortError,
    SearchUnavailableError,
    verify_quote,
)
from app.services.quote_verifier import normalise_for_match

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


@router.get("/claim", response_model=ClaimVerdict)
async def verify_claim_endpoint(
    q: str = Query(..., min_length=1, max_length=200, description="待核对的一句「佛说」"),
    db: AsyncSession = Depends(get_db),
) -> ClaimVerdict:
    """「这句经，佛真的说过吗？」——给人看的核对（/verify 页与结果图）。

    Whole text first, then clause by clause; the verdict says whether it is in
    a sūtra, only in later works, partly, or not at all. Up to 1 + 8 lookups per
    call, hence its own, stricter limit (rate_limit_verify_claim)."""
    es: AsyncElasticsearch = get_es()
    try:
        return await check_claim(db, es, q)
    except QuoteTooShortError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SearchUnavailableError as exc:
        raise HTTPException(status_code=503, detail="search temporarily unavailable") from exc



# ── fojin.ai 首页「引文溯源」：整段文字逐句核对 ─────────────────────────────
# 页面在浏览器里把一段文字切成句子，每次送最多 TRACE_MAX_SENTENCES 句，
# 边查边显示。每句走与 /claim 相同的 check_claim（整句 → 分句，共用缓存）。

TRACE_MAX_SENTENCES = 8

TraceSentence = Annotated[str, StringConstraints(min_length=1, max_length=200)]


class TraceRequest(BaseModel):
    sentences: list[TraceSentence] = Field(..., min_length=1, max_length=TRACE_MAX_SENTENCES)


class TraceItem(BaseModel):
    text: str
    result: ClaimVerdict | None = None
    # "too_short"：去掉标点后不足以查找（如「好的。」），原样显示、不着色
    skipped: str | None = None


class TraceResponse(BaseModel):
    items: list[TraceItem]


@router.post("/trace", response_model=TraceResponse)
async def trace_endpoint(
    body: TraceRequest,
    db: AsyncSession = Depends(get_db),
) -> TraceResponse:
    """逐句核对一段文字里哪些句子出自藏经（fojin.ai 首页）。

    Up to 8 sentences per call, each checked like /claim (whole sentence, then
    clause by clause), hence its own limit (rate_limit_verify_trace). A search
    outage fails the whole call (503) rather than reading as "not found"."""
    es: AsyncElasticsearch = get_es()
    items: list[TraceItem] = []
    for sentence in body.sentences:
        if len(normalise_for_match(sentence)) < MIN_LOOKUP_QUOTE_CHARS:
            items.append(TraceItem(text=sentence, skipped="too_short"))
            continue
        try:
            verdict = await credit_runs(db, es, await check_claim(db, es, sentence))
            items.append(TraceItem(text=sentence, result=verdict))
        except QuoteTooShortError:
            items.append(TraceItem(text=sentence, skipped="too_short"))
        except SearchUnavailableError as exc:
            raise HTTPException(status_code=503, detail="search temporarily unavailable") from exc
    return TraceResponse(items=items)
