"""Rescue correct citations of texts retrieval did not surface.

The citation guard only trusts titles among *this answer's* retrieved sources:
a 【《X》第N卷】 naming any other text loses its clickable wrapper. That is the
right default — the model is not allowed to invent sources — but it also
strips citations that are simply correct. Measured 2026-11-16 over 30 days of
production answers: of 124 「unverified title」 rewrites, 36 carried a quote that
``/verify/quote`` confirmed verbatim in exactly the text the model named. The
model knew the source; retrieval (which favours dense commentaries) just did
not bring it back.

This module checks those citations against the corpus before the guard runs.
When the quote right before the marker is found verbatim in the named text, the
fascicle that holds it is added to ``sources`` — so the guard keeps the
citation (correcting the fascicle if the model's number was off), the quote
verifier sees the passage, and the frontend can link it. Anything less than a
verbatim hit in the named text leaves the answer exactly as before.

Fail-open by construction: the caller bounds it with a timeout and treats any
exception as "nothing rescued".
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass

from elasticsearch import AsyncElasticsearch
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.chat import ChatSource
from app.services.citation_guard import _CITATION_RE, _build_whitelist, _norm_title, _parse_juan
from app.services.quote_lookup import QuoteTooShortError, verify_quote
from app.services.quote_verifier import MAX_QUOTE_CITATION_GAP_CHARS, normalise_for_match

logger = logging.getLogger(__name__)

# A quote this short can still pin a passage inside one named text (we never ask
# "where in the whole canon", only "is it in this book"); production rescues
# include 8-char lines such as 「諸有漏慧皆智性攝」.
MIN_RESCUE_QUOTE_CHARS = 8
# Each check is one ES + DB round trip; an answer rarely has more than a couple.
MAX_RESCUES_PER_ANSWER = 4
_INDEX_TTL_S = 6 * 3600

_RANGE_RE = re.compile(r"[（(]第([0-9]+)卷-第([0-9]+)卷[)）]\s*$")

# Same shape as quote_verifier's preceding-quote pattern (a 「…」 right before the
# marker, at most a few characters apart), but from 8 characters: the verifier's
# 12-character floor is about judging paraphrase, while here the question is only
# whether this exact line occurs in one named text.
_QUOTE_BEFORE_RE = re.compile(
    r"[「『“‘\"]"
    r"([^「『“‘\"」』”’]{" + str(MIN_RESCUE_QUOTE_CHARS) + r",400})"
    r"[」』”’\"]"
    r"[^【】「『“‘\"」』”’]{0," + str(MAX_QUOTE_CITATION_GAP_CHARS) + r"}$"
)


@dataclass(frozen=True)
class _Part:
    text_id: int
    cbeta_id: str
    lo: int | None  # fascicle range of a split work's part; None when unsplit
    hi: int | None


_index: dict[str, list[_Part]] | None = None
_index_at = 0.0
_index_lock = asyncio.Lock()


async def _title_index(db: AsyncSession) -> dict[str, list[_Part]]:
    """{normalised title → parts}. Split works (大般若經 has 15 parts) map one
    title to several rows, each with its absolute fascicle range."""
    global _index, _index_at
    if _index is not None and time.monotonic() - _index_at < _INDEX_TTL_S:
        return _index
    async with _index_lock:
        if _index is not None and time.monotonic() - _index_at < _INDEX_TTL_S:
            return _index
        rows = (
            await db.execute(
                sql_text(
                    "SELECT id, cbeta_id, title_zh FROM buddhist_texts "
                    "WHERE has_content AND cbeta_id IS NOT NULL AND title_zh IS NOT NULL"
                )
            )
        ).all()
        idx: dict[str, list[_Part]] = {}
        for text_id, cbeta_id, title in rows:
            m = _RANGE_RE.search(title)
            lo, hi = (int(m.group(1)), int(m.group(2))) if m else (None, None)
            idx.setdefault(_norm_title(title), []).append(_Part(text_id, cbeta_id, lo, hi))
        _index, _index_at = idx, time.monotonic()
        return idx


def _pick_part(parts: list[_Part], juan: int | None) -> _Part | None:
    """The one text a citation names. For a split work, the part whose range
    holds the cited fascicle; without a fascicle that is ambiguous → None."""
    if len(parts) == 1:
        return parts[0]
    if juan is None:
        return None
    for p in parts:
        if p.lo is not None and p.hi is not None and p.lo <= juan <= p.hi:
            return p
    return None


def rescue_candidates(answer: str, sources: list[ChatSource]) -> list[tuple[str, int | None, str]]:
    """Citations worth checking, as (normalised title, cited juan, quote).

    Pure text work — the chat path calls this first and only opens a DB
    session when it returns something (most answers: nothing)."""
    if not answer or "【《" not in answer:
        return []
    whitelist = _build_whitelist(sources)
    pending: list[tuple[str, int | None, str]] = []
    seen: set[tuple[str, str]] = set()
    for m in _CITATION_RE.finditer(answer):
        title = _norm_title(m.group(1))
        if not title or title in whitelist:
            continue
        qm = _QUOTE_BEFORE_RE.search(answer[: m.start()])
        quote = qm.group(1).strip() if qm else None
        if not quote or len(normalise_for_match(quote)) < MIN_RESCUE_QUOTE_CHARS:
            continue
        key = (title, normalise_for_match(quote))
        if key in seen:
            continue
        seen.add(key)
        juan, _ = _parse_juan(m.group(2))
        pending.append((title, juan, quote))
        if len(pending) >= MAX_RESCUES_PER_ANSWER:
            break
    return pending


async def rescue_unretrieved_citations(
    answer: str,
    sources: list[ChatSource],
    db: AsyncSession,
    es: AsyncElasticsearch,
) -> list[ChatSource]:
    """Sources to append so that verbatim-correct citations survive the guard.

    Returns an empty list when nothing qualifies. Never mutates ``sources``.
    """
    pending = rescue_candidates(answer, sources)
    if not pending:
        return []

    index = await _title_index(db)
    rescued: list[ChatSource] = []
    added: set[tuple[int, int]] = set()
    for title, juan, quote in pending:
        part = _pick_part(index.get(title, []), juan)
        if part is None:
            continue
        try:
            verdict = await verify_quote(db, es, quote, cite=part.cbeta_id)
        except QuoteTooShortError:
            continue
        if not verdict.verbatim or not verdict.cite_matched:
            continue
        hit = next((x for x in verdict.matches if x.text_id == part.text_id), None)
        if hit is None or (hit.text_id, hit.juan_num) in added:
            continue
        added.add((hit.text_id, hit.juan_num))
        rescued.append(
            ChatSource(
                text_id=hit.text_id,
                juan_num=hit.juan_num,
                # No chunk of this fascicle was retrieved: -1 tells the frontend
                # to open the whole fascicle and highlight the quote there.
                chunk_index=-1,
                chunk_text=quote,
                score=0.0,
                title_zh=hit.title_zh or "",
                urn=hit.urn,
            )
        )
    return rescued
