"""Public quote-verification endpoint — the AI-facing half of fojin's
"每一句都能点回原典" contract.

GET /api/verify/quote?q=…&cite=…&juan=…

Any agent that has written a Buddhist-canon quote can ask, in one call,
whether that quote exists verbatim in the corpus (and where), instead of
serving its readers an invented citation. Read-only; strict-rate-limited
(paid nothing, but ES + source-text reads are not free).
"""

import re
from typing import Annotated

from elasticsearch import AsyncElasticsearch
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.elasticsearch import get_es
from app.database import get_db
from app.schemas.verification import ClaimVerdict, QuoteMatch, QuoteVerdict
from app.services.claim_check import attribute_by_context, check_claim, credit_runs
from app.services.machine_citation_api import enrich_verdict
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
        verdict = await verify_quote(db, es, q, cite=cite, juan=juan)
    except QuoteTooShortError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # 开放接口专属：前几条命中补行号、行级 URN、可粘贴引用、许可署名（问答链路不走这里）
    return await enrich_verdict(db, verdict)


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

# 引语前缀：句首十几个字以内、以「说/云/曰/言/道/讲」(+过) 收尾、后接冒号或逗号。
# 先整句核对——「論曰：」「頌曰：」「佛言：」常是藏经原文的一部分；整句找不到时才去掉
# 前缀重查（「佛说：一切有为法……」「《金刚经》说：『……』」）。与 trace.js 早先的规则一致。
_ATTRIBUTION_RE = re.compile(
    r"^([^，。；：:「“\"]{0,14}?(?:说|說|云|曰|言|道|讲|講|有言|有云)(?:过|過)?)\s*[：:，,]\s*"
)


def _split_attribution(sentence: str) -> tuple[str, str]:
    m = _ATTRIBUTION_RE.match(sentence)
    if not m:
        return "", sentence
    body = sentence[m.end():]
    if len(normalise_for_match(body)) < MIN_LOOKUP_QUOTE_CHARS:
        return "", sentence
    return m.group(0), body


def _found_whole(v: ClaimVerdict) -> bool:
    """The sentence as typed is a canon line — one segment, verbatim or a
    wording variant. Clauses that are each found somewhere do not count: the
    prefix 「《金刚经》说」 merges into one clause that happens to occur in the
    大智度論, and the sentence would be credited there."""
    return len(v.segments) == 1 and (v.segments[0].found or v.segments[0].close is not None)

TraceSentence = Annotated[str, StringConstraints(min_length=1, max_length=200)]


class TraceRequest(BaseModel):
    sentences: list[TraceSentence] = Field(..., min_length=1, max_length=TRACE_MAX_SENTENCES)
    # 上一批的主出处（上一次响应的 dominant，原样送回）：一段文字跨批时，常见短句
    # 仍按这段原文的出处认（见 attribute_by_context）。
    prefer: QuoteMatch | None = None


class TraceItem(BaseModel):
    text: str
    result: ClaimVerdict | None = None
    # 「佛说：」「经云：」这类引语前缀：整句在藏经里找不到时去掉它再查，
    # result 对应的是去掉前缀后的文字；页面把前缀灰显。
    prefix: str | None = None
    # "too_short"：去掉标点后不足以查找（如「好的。」），原样显示、不着色
    skipped: str | None = None


class TraceResponse(BaseModel):
    items: list[TraceItem]
    # 这一批（连同 prefer）主要出自的那一卷；页面在下一批里作为 prefer 送回。
    dominant: QuoteMatch | None = None


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
            prefix, bare_text = _split_attribution(sentence)
            if prefix and not _found_whole(verdict):
                bare = await credit_runs(db, es, await check_claim(db, es, bare_text))
                if bare.verdict != "absent":
                    items.append(TraceItem(text=sentence, result=bare, prefix=prefix))
                    continue
            items.append(TraceItem(text=sentence, result=verdict))
        except QuoteTooShortError:
            items.append(TraceItem(text=sentence, skipped="too_short"))
        except SearchUnavailableError as exc:
            raise HTTPException(status_code=503, detail="search temporarily unavailable") from exc
    attributed, dominant = await attribute_by_context(db, [i.result for i in items], body.prefer)
    items = [i.model_copy(update={"result": r}) for i, r in zip(items, attributed, strict=True)]
    return TraceResponse(items=items, dominant=dominant)
