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

from app.schemas.verification import ClaimSegment, ClaimVerdict, ClosestMiss, QuoteVerdict
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
    """Punctuation-delimited clauses, each long enough to look up.

    At most MAX_CLAUSES: anything past the cap is merged into the last clause
    rather than dropped — a fabricated line after eight real ones must still be
    checked, or the page would call the whole thing a sūtra line.
    """
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
    if len(clauses) > MAX_CLAUSES:
        clauses = clauses[: MAX_CLAUSES - 1] + ["".join(clauses[MAX_CLAUSES - 1 :])]
    return clauses


# A near miss counts as "the canon has it, worded slightly differently" only
# when the differences are character substitutions, at most this many: 莲花/蓮華,
# 其土/其國, 我禮/我供. An insertion or deletion is an addition or an omission —
# 「不應作如是觀」 reverses the meaning, 「…應作如是觀，放下吧」 appends a tail —
# and must not be presented as a wording variant.
MAX_VARIANT_SUBSTITUTIONS = 2


def _is_wording_variant(close: ClosestMiss | None) -> bool:
    if close is None or not close.diff:
        return False
    changed = [op for op in close.diff if op.op != "equal"]
    if not changed or any(op.op != "replace" for op in changed):
        return False
    return sum(len(op.quote) for op in changed) <= MAX_VARIANT_SUBSTITUTIONS


def _segment(text: str, verdict: QuoteVerdict) -> ClaimSegment:
    seen: set[str] = set()
    distinct = []
    for m in verdict.matches:  # earliest-in-canon first
        key = m.title_zh or m.cbeta_id or str(m.text_id)
        if key not in seen:
            seen.add(key)
            distinct.append(m)
    # A sūtra occurrence is the answer to「佛说的吗」— list it first even when a
    # treatise or commentary with a lower catalogue number also has the line.
    distinct.sort(key=lambda m: m.canon_class != "sutra")
    close = verdict.closest if (not verdict.verbatim and verdict.bucket == "near_miss") else None
    return ClaimSegment(
        text=text,
        found=verdict.verbatim,
        sources=distinct[:MAX_SOURCES_PER_SEGMENT],
        similarity=verdict.similarity,
        close=close if _is_wording_variant(close) else None,
    )


def _overall(query: str, segments: list[ClaimSegment]) -> ClaimVerdict:
    found = [s for s in segments if s.found]
    close = [s for s in segments if not s.found and s.close is not None]
    if not found and not close:
        return ClaimVerdict(query=query, verdict="absent", segments=segments)
    if len(found) + len(close) < len(segments):
        return ClaimVerdict(query=query, verdict="partial", segments=segments)

    def seg_class(s: ClaimSegment) -> str | None:
        if s.found:
            return "sutra" if any(m.canon_class == "sutra" for m in s.sources) else (
                s.sources[0].canon_class if s.sources else None
            )
        return s.close.canon_class if s.close else None

    classes = [seg_class(s) for s in segments]
    if close:
        cls = "sutra" if all(c == "sutra" for c in classes) else next(c for c in classes if c != "sutra")
        return ClaimVerdict(query=query, verdict="variant", source_class=cls, segments=segments)
    if all(c == "sutra" for c in classes):
        return ClaimVerdict(query=query, verdict="sutra", source_class="sutra", segments=segments)
    first_other = next(c for c in classes if c != "sutra")
    return ClaimVerdict(query=query, verdict="not_sutra", source_class=first_other, segments=segments)


async def check_claim(db: AsyncSession, es: AsyncElasticsearch, text: str) -> ClaimVerdict:
    # Keyed by the input as typed: punctuation decides how it is split, so two
    # texts that normalise alike can still deserve different answers.
    key = text.strip()
    hit = _CACHE.get(key)
    now = time.monotonic()
    if hit is not None and now - hit[0] < _CACHE_TTL:
        return hit[1]

    # strict: a search outage raises (→ 503) instead of reading as "not found",
    # and nothing is cached.
    whole = await verify_quote(db, es, text, strict=True)  # QuoteTooShortError if too short
    clauses = split_clauses(text)
    if whole.verbatim or len(clauses) <= 1:
        segments = [_segment(text, whole)]
    else:
        segments = [_segment(c, await verify_quote(db, es, c, strict=True)) for c in clauses]
    result = _overall(text, segments)

    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))  # oldest insertion
    _CACHE[key] = (now, result)
    return result
