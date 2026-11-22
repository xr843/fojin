"""Where in a fascicle a verified quote sits, as a CBETA line (``0947a16``).

Verification only proves the quote is *in* the fascicle; a reader link to the
fascicle then drops the reader at its first page. The reader already jumps to
and highlights a line given ``?anchor=p<line_ref>``, and every fascicle has its
``<lb>`` markers stored with character offsets (``text_line_anchors``), so the
missing piece is the quote's offset in the stored text.

The verifier compares in normalised space (NFKC, 繁→简, variant fold,
punctuation stripped), which cannot be mapped back to source offsets when done
on a whole string. Here every character is normalised on its own, so each
normalised character remembers the source offset it came from. The quote is
normalised the same way (character by character), so both sides agree even
where OpenCC's phrase-level conversion would not.
"""

from bisect import bisect_right

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.text import TextContent, TextLineAnchor
from app.services.quote_verifier import normalise_for_match

_CHAR_CACHE: dict[str, str] = {}


def _norm_char(ch: str) -> str:
    out = _CHAR_CACHE.get(ch)
    if out is None:
        out = normalise_for_match(ch)
        if len(_CHAR_CACHE) < 50_000:
            _CHAR_CACHE[ch] = out
    return out


def _normalise(s: str) -> str:
    return "".join(_norm_char(ch) for ch in s)


def _index(content: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    origin: list[int] = []
    for i, ch in enumerate(content):
        for c in _norm_char(ch):
            chars.append(c)
            origin.append(i)
    return "".join(chars), origin


_OPENERS = set("「『“‘《〈（(〔［[")
_MAX_EDGE_PUNCT = 3


def _is_punct(ch: str) -> bool:
    # Anything the normaliser drops (punctuation, spaces) counts; a Han
    # character or a letter never does.
    return ch.strip() != "" and _norm_char(ch) == ""


def locate_span(content: str, quote: str, index: tuple[str, list[int]] | None = None) -> tuple[int, int] | None:
    """Offsets in ``content`` of the quote's first and last character
    (inclusive), compared in normalised space. Punctuation the source has
    inside the quote is covered. Punctuation at its edges is covered only when
    the quote itself has some there — 「……法門。」 highlights the source's 。
    too (user screenshot, 2026-11-22), a bare clause 「……法門」 does not."""
    needle = _normalise(quote)
    if not needle:
        return None
    normalised, origin = index if index is not None else _index(content)
    at = normalised.find(needle)
    if at < 0:
        return None
    first, last = origin[at], origin[at + len(needle) - 1]
    stripped = quote.strip()
    if stripped and _is_punct(stripped[-1]):
        k = 0
        while k < _MAX_EDGE_PUNCT and last + 1 < len(content) and _is_punct(content[last + 1]):
            last += 1
            k += 1
    if stripped and stripped[0] in _OPENERS:
        k = 0
        while k < _MAX_EDGE_PUNCT and first > 0 and content[first - 1] in _OPENERS:
            first -= 1
            k += 1
    return first, last


def locate_offset(content: str, quote: str, index: tuple[str, list[int]] | None = None) -> int | None:
    """Offset in ``content`` where ``quote`` starts, compared in normalised space."""
    span = locate_span(content, quote, index)
    return span[0] if span else None


# (text_id, juan) → (content, normalised text, source offsets, line markers). A sentence
# split into clauses, or a page of sentences from one sūtra, hits the same
# fascicle again and again; a few dozen entries cover a request comfortably.
_FASCICLES: dict[tuple[int, int], tuple[str, str, list[int], list[tuple[int, str]]]] = {}
_FASCICLES_MAX = 32


def nearest_line(anchors: list[tuple[int, str]], offset: int) -> str | None:
    """The line marker at or before ``offset``; ``anchors`` sorted by offset."""
    i = bisect_right([off for off, _ in anchors], offset) - 1
    return anchors[i][1] if i >= 0 else None


async def locate_quote(
    db: AsyncSession, text_id: int, juan: int, quote: str
) -> tuple[str | None, int, int] | None:
    """Where the quote sits in the fascicle: ``(p<line_ref> or None, first, last)``
    — the line for the reader's ``?anchor=`` and the character span for its
    ``?hl=`` (the whole quote stays highlighted). None when the fascicle or
    the quote cannot be found; the caller then keeps its fascicle-level link."""
    key = (text_id, juan)
    cached = _FASCICLES.get(key)
    if cached is None:
        content = (
            await db.execute(
                select(TextContent.content).where(
                    TextContent.text_id == text_id,
                    TextContent.juan_num == juan,
                    TextContent.lang == "lzh",
                )
            )
        ).scalar_one_or_none()
        if not content:
            return None
        anchors = [
            (off, ref)
            for off, ref in (
                await db.execute(
                    select(TextLineAnchor.char_offset, TextLineAnchor.line_ref)
                    .where(TextLineAnchor.text_id == text_id, TextLineAnchor.juan_num == juan)
                    .order_by(TextLineAnchor.char_offset)
                )
            ).all()
        ]
        normalised, origin = _index(content)
        cached = (content, normalised, origin, anchors)
        if len(_FASCICLES) >= _FASCICLES_MAX:
            _FASCICLES.pop(next(iter(_FASCICLES)))
        _FASCICLES[key] = cached
    content, normalised, origin, anchors = cached
    span = locate_span(content, quote, index=(normalised, origin))
    if span is None:
        return None
    ref = nearest_line(anchors, span[0])
    return (f"p{ref}" if ref else None), span[0], span[1]
