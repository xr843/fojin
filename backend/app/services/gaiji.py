"""CBETA gaiji (rare-character) normalization service.

A gaiji is a Chinese character that lacks a standard Unicode code point
at digitization time. CBETA encodes them inline as composition
expressions like ``[木*奈]`` or PUA codepoints like ``U+F0001``. Without
normalization, full-text search systematically under-recalls passages
containing such characters: a user searching for "款" never matches a
passage encoded as ``[肄-聿+欠]``.

This service exposes two operations:

1. :func:`normalize_for_index` — used at ES index time. Returns a copy
   of the text with all composition expressions and PUA codepoints
   replaced by their best Unicode equivalent. Unmatched compositions
   are preserved verbatim (they may be valid bracket text for
   non-gaiji reasons, or a gaiji not yet in the upstream table).

2. :func:`expand_for_query` — used at query analysis time. Given a
   single plain character, returns the set of alternate spellings
   under which the same gaiji might appear in source text (composition
   plus PUA codepoint), for ES OR-expansion.

Both operations are sync and pure (given a built normalizer). The
normalizer itself is built once at backend startup from the
``gaiji`` table (~31k entries, ~10MB in-memory). If upstream gaiji
changes, rebuild and replace the snapshot rather than mutating it.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gaiji import Gaiji

logger = logging.getLogger(__name__)


# CBETA composition expressions: ``[...]`` where the inner content has
# no closing bracket. Nesting is via parentheses, never square brackets,
# so a flat regex is sufficient. The ``+`` is intentional — empty ``[]``
# is never valid gaiji syntax and we don't want to match stray brackets.
_COMPOSITION_RE = re.compile(r"\[[^\]]+\]")

# CBETA PUA codepoints written textually, ``U+F0001`` through ``U+FFFFF``.
# Some legacy CBETA files embed these as ASCII rather than as the
# corresponding PUA glyph, hence textual matching.
_PUA_TEXT_RE = re.compile(r"U\+F[0-9A-F]{4}")


@dataclass(frozen=True, slots=True)
class GaijiNormalizer:
    """Immutable snapshot of the gaiji table for sync lookup.

    Three reverse-index dictionaries are precomputed at build time so
    ``normalize_for_index`` and ``expand_for_query`` run in O(text)
    rather than per-character DB lookups.
    """

    # composition string → best Unicode equivalent (norm_uni_char fallback unicode_char)
    composition_to_norm: dict[str, str]
    # PUA textual codepoint → best Unicode equivalent
    pua_to_norm: dict[str, str]
    # Any Unicode form of a gaiji → set of alternate spellings (composition + PUA)
    glyph_to_alternates: dict[str, frozenset[str]]

    def size(self) -> int:
        """Total number of distinct entries indexed (for diagnostics)."""
        return len(self.composition_to_norm) + len(self.pua_to_norm)


async def build_normalizer(db: AsyncSession) -> GaijiNormalizer:
    """Load the full gaiji table and build the in-memory normalizer.

    Should be called once at backend startup. The resulting snapshot
    is safe to share across requests; do not mutate.
    """
    rs = await db.execute(
        select(
            Gaiji.composition,
            Gaiji.unicode_char,
            Gaiji.norm_unicode_char,
            Gaiji.norm_big5_char,
            Gaiji.pua_codepoint,
        )
    )

    composition_to_norm: dict[str, str] = {}
    pua_to_norm: dict[str, str] = {}
    glyph_to_alternates_mut: dict[str, set[str]] = {}

    for comp, uni, norm_uni, norm_big5, pua in rs.all():
        # Best Unicode equivalent: norm_uni_char is CBETA's canonical
        # search target when assigned (BMP-range, font-safe); otherwise
        # fall back to unicode_char (formal Unicode if any).
        best = norm_uni or uni

        if comp and best:
            composition_to_norm[comp] = best
        if pua and best:
            pua_to_norm[pua] = best

        # Reverse index for query expansion. Any Unicode form a user
        # might type maps back to all gaiji spellings.
        for glyph in (uni, norm_uni, norm_big5):
            if not glyph:
                continue
            alts = glyph_to_alternates_mut.setdefault(glyph, set())
            if comp:
                alts.add(comp)
            if pua:
                alts.add(pua)

    normalizer = GaijiNormalizer(
        composition_to_norm=composition_to_norm,
        pua_to_norm=pua_to_norm,
        glyph_to_alternates={k: frozenset(v) for k, v in glyph_to_alternates_mut.items()},
    )
    logger.info(
        "gaiji normalizer built: %d compositions, %d pua, %d glyphs reverse-indexed",
        len(composition_to_norm),
        len(pua_to_norm),
        len(glyph_to_alternates_mut),
    )
    return normalizer


def normalize_for_index(text: str, normalizer: GaijiNormalizer) -> str:
    """Replace gaiji compositions and PUA codepoints with Unicode equivalents.

    Two passes: composition expressions first, then PUA codepoints.
    Unmatched compositions are preserved verbatim.
    """
    if not text:
        return text

    def _comp_repl(match: re.Match[str]) -> str:
        comp = match.group(0)
        return normalizer.composition_to_norm.get(comp, comp)

    text = _COMPOSITION_RE.sub(_comp_repl, text)

    def _pua_repl(match: re.Match[str]) -> str:
        pua = match.group(0)
        return normalizer.pua_to_norm.get(pua, pua)

    return _PUA_TEXT_RE.sub(_pua_repl, text)


def expand_for_query(token: str, normalizer: GaijiNormalizer) -> frozenset[str]:
    """Return alternate spellings the token might appear under in source text.

    For multi-character tokens, only the first character is considered:
    gaiji is a per-character phenomenon and multi-char tokens should be
    expanded char-by-char by the caller. Returns an empty frozenset
    when no alternates are known — caller may use the original token
    unchanged.
    """
    if not token:
        return frozenset()
    return normalizer.glyph_to_alternates.get(token[0], frozenset())
