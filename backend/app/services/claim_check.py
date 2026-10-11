"""「这句经，佛真的说过吗？」— check a pasted saying clause by clause.

The most common fake "Buddha said" is a real line with an invented tail
(「一切有为法，如梦幻泡影，看开便是福」): checked as one string it is simply
"absent", which is true and misleading. So the whole text is tried first, and
if it is not verbatim, each clause is checked on its own. The overall verdict
then says whether it is in a sūtra, only in later works, partly, or not at all.
See docs/superpowers/specs/2026-10-11-verify-page-design.md §3.3.
"""

import re
import time

from elasticsearch import AsyncElasticsearch
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.verification import ClaimSegment, ClaimVerdict, QuoteVerdict
from app.services.quote_lookup import MIN_LOOKUP_QUOTE_CHARS, verify_quote
from app.services.quote_verifier import normalise_for_match

MAX_CLAUSES = 8
MAX_SOURCES_PER_SEGMENT = 3
_CACHE_TTL = 3600.0
_CACHE_MAX = 512
# normalised text → (stored_at, verdict). Shared by the API and the result
# image so rendering a shared link does not redo the lookups.
_CACHE: dict[str, tuple[float, ClaimVerdict]] = {}

_CLAUSE_SPLIT_RE = re.compile(r"[，。；：！？、,.;:!?\s「」『』“”‘’（）()《》〈〉…—]+")


def split_clauses(text: str) -> list[str]:
    """Punctuation-delimited clauses, each long enough to look up, at most MAX_CLAUSES."""
    parts = [p for p in _CLAUSE_SPLIT_RE.split(text) if p]
    clauses: list[str] = []
    for part in parts:
        if clauses and len(normalise_for_match(clauses[-1])) < MIN_LOOKUP_QUOTE_CHARS:
            clauses[-1] += part  # previous fragment too short on its own
        else:
            clauses.append(part)
    if len(clauses) > 1 and len(normalise_for_match(clauses[-1])) < MIN_LOOKUP_QUOTE_CHARS:
        tail = clauses.pop()
        clauses[-1] += tail
    return clauses[:MAX_CLAUSES]


def _segment(text: str, verdict: QuoteVerdict) -> ClaimSegment:
    seen: set[str] = set()
    sources = []
    for m in verdict.matches:  # already earliest-in-canon first
        key = m.title_zh or m.cbeta_id or str(m.text_id)
        if key in seen:
            continue
        seen.add(key)
        sources.append(m)
        if len(sources) == MAX_SOURCES_PER_SEGMENT:
            break
    close = verdict.closest if (not verdict.verbatim and verdict.bucket == "near_miss") else None
    return ClaimSegment(
        text=text, found=verdict.verbatim, sources=sources, similarity=verdict.similarity, close=close
    )


def _overall(query: str, segments: list[ClaimSegment]) -> ClaimVerdict:
    found = [s for s in segments if s.found]
    close = [s for s in segments if not s.found and s.close is not None]
    if not found and not close:
        return ClaimVerdict(query=query, verdict="absent", segments=segments)
    if len(found) + len(close) < len(segments):
        return ClaimVerdict(query=query, verdict="partial", segments=segments)
    if close:
        first = segments[0]
        cls = first.sources[0].canon_class if first.found and first.sources else (first.close and first.close.canon_class)
        return ClaimVerdict(query=query, verdict="variant", source_class=cls, segments=segments)
    classes = [s.sources[0].canon_class if s.sources else None for s in segments]
    if all(c == "sutra" for c in classes):
        return ClaimVerdict(query=query, verdict="sutra", source_class="sutra", segments=segments)
    first_other = next(c for c in classes if c != "sutra")
    return ClaimVerdict(query=query, verdict="not_sutra", source_class=first_other, segments=segments)


async def check_claim(db: AsyncSession, es: AsyncElasticsearch, text: str) -> ClaimVerdict:
    key = normalise_for_match(text)
    hit = _CACHE.get(key)
    now = time.monotonic()
    if hit is not None and now - hit[0] < _CACHE_TTL:
        return hit[1]

    whole = await verify_quote(db, es, text)  # raises QuoteTooShortError if too short
    clauses = split_clauses(text)
    # A whole-text near miss (a character or two off the canon) is answered as
    # one variant segment: splitting it would turn「莲花/蓮華」into a clause
    # that is merely "missing", which is exactly the wrong message.
    if whole.verbatim or whole.bucket == "near_miss" or len(clauses) <= 1:
        segments = [_segment(text, whole)]
    else:
        segments = [_segment(c, await verify_quote(db, es, c)) for c in clauses]
    result = _overall(text, segments)

    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))  # oldest insertion
    _CACHE[key] = (now, result)
    return result
