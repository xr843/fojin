"""Schemas for the public quote-verification API (/api/verify/quote).

The response is designed for AI-agent consumers: every claim the verdict
makes is either machine-checkable (URNs resolve via /api/urn/resolve) or
explicitly caveated (``caveats``). ``verbatim`` answers the open-world
question — "does this quote exist verbatim anywhere in the corpus?" — which
is deliberately different from the chat pipeline's closed-world check
against a single answer's retrieved chunks.
"""

from typing import Literal

from pydantic import BaseModel


class QuoteMatch(BaseModel):
    """One fascicle where the quote was confirmed verbatim (substring test
    on the normalised source text — the authoritative check, not ES)."""

    text_id: int
    cbeta_id: str | None = None
    title_zh: str | None = None
    juan_num: int
    urn: str | None = None
    # True/False only when the caller hinted a juan; None otherwise.
    juan_matched: bool | None = None


class ClosestMiss(BaseModel):
    """Best near-match window when the quote is NOT verbatim anywhere we
    looked. ``window_normalised`` is in normalised space (NFKC + 繁→简 +
    punctuation stripped) — the exact space the verdict is computed in."""

    text_id: int
    juan_num: int
    urn: str | None = None
    similarity: float
    window_normalised: str


class QuoteVerdict(BaseModel):
    quote: str
    normalised_quote: str
    verbatim: bool
    bucket: Literal["exact", "near_miss", "absent"]
    # 1.0 for exact; otherwise the best windowed SequenceMatcher ratio found.
    similarity: float
    matches: list[QuoteMatch] = []
    closest: ClosestMiss | None = None
    # None when no cite hint was given.
    cite_resolved: bool | None = None
    # True when the quote was confirmed inside the hinted text (and juan, if
    # one was hinted). Deliberately NOT inherited from the chat verifier's
    # any-juan fallback — a quote found in juan 16 does not validate a
    # citation claiming juan 13.
    cite_matched: bool | None = None
    lang: str = "lzh"
    caveats: list[str] = []
