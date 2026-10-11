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

__all__ = ["ClosestMiss", "DiffOp", "QuoteMatch", "QuoteVerdict"]


class QuoteMatch(BaseModel):
    """One fascicle where the quote was confirmed verbatim (substring test
    on the normalised source text — the authoritative check, not ES)."""

    text_id: int
    cbeta_id: str | None = None
    title_zh: str | None = None
    juan_num: int
    urn: str | None = None
    # Absolute, so the caller can render a citation someone can click. A
    # relative path is unusable to an agent with no host in hand — it links
    # elsewhere instead, and the verification fojin performed goes uncredited.
    reader_url: str | None = None
    # True/False only when the caller hinted a juan; None otherwise.
    juan_matched: bool | None = None
    # Which part of the canon this source belongs to (sutra / vinaya /
    # treatise / commentary / school / history / apocrypha / later / unknown)
    # — see app/services/canon_class.py. Matches arrive earliest-in-canon first.
    canon_class: str | None = None


class DiffOp(BaseModel):
    """One span of agreement or disagreement between the submitted quote and
    the closest source window, in normalised space.

    ``quote`` is what the caller sent, ``source`` is what the canon actually
    reads. For ``equal`` both are the same text; for ``delete`` the source
    side is empty (the caller has words the source does not) and for
    ``insert`` the quote side is empty (the source has words the caller
    dropped)."""

    op: Literal["equal", "replace", "delete", "insert"]
    quote: str
    source: str


class ClosestMiss(BaseModel):
    """Best near-match window when the quote is NOT verbatim anywhere we
    looked. ``window_normalised`` is in normalised space (NFKC + 繁→简 +
    punctuation stripped) — the exact space the verdict is computed in."""

    text_id: int
    juan_num: int
    urn: str | None = None
    reader_url: str | None = None
    similarity: float
    window_normalised: str
    # Character-level differences against window_normalised. Reported in
    # normalised space only: normalisation folds 繁→简 phrase-wise and drops
    # punctuation, so a character index cannot be mapped back to the original
    # text without inventing an alignment. Saying "here, in the space the
    # verdict was computed in" is answerable; "here, in your original string"
    # is not.
    diff: list[DiffOp] = []
    # Which text the closest window is in — added for the human-facing /verify
    # page, which names it ("the canon has this line, worded slightly
    # differently, in 《…》"). Optional so older consumers are unaffected.
    cbeta_id: str | None = None
    title_zh: str | None = None
    canon_class: str | None = None


class QuoteVerdict(BaseModel):
    quote: str
    normalised_quote: str
    verbatim: bool
    bucket: Literal["exact", "near_miss", "absent"]
    # 1.0 for exact; otherwise the best windowed SequenceMatcher ratio found.
    similarity: float
    matches: list[QuoteMatch] = []
    # True when the match list hit its cap. It does not prove more exist, but
    # it does mean this list is a sample rather than the complete answer —
    # which matters most for short quotes, where a phrase can recur in
    # hundreds of texts.
    matches_capped: bool = False
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


# ── 「这句经，佛真的说过吗？」 (GET /api/verify/claim) ─────────────────────


class ClaimSegment(BaseModel):
    """One clause of the pasted text and where (if anywhere) it is found."""

    text: str
    found: bool
    # Up to three distinct titles, earliest-in-canon first.
    sources: list[QuoteMatch] = []
    similarity: float = 0.0
    # Not verbatim but a near miss (similarity ≥ NEAR_MISS_THRESHOLD): where
    # the canon has it, and in what words. Only set when found is False.
    close: ClosestMiss | None = None


class ClaimVerdict(BaseModel):
    """Human-facing answer for the /verify page and its result image.

    verdict:
      sutra      — every clause is found, and found in a sūtra (经藏/密教/南传汉译)
      not_sutra  — every clause is found, but not in a sūtra; see source_class
      variant    — the canon has it, worded slightly differently (near miss);
                   source_class says where — the popular 莲花 vs the canon's 蓮華
      partial    — some clauses are found, some are not
      absent     — nothing is found in the canon
    Wording rule for consumers: "sutra" means 出自佛经, never 佛亲口所说 —
    sūtras also record what bodhisattvas and disciples said.
    """

    query: str
    verdict: Literal["sutra", "not_sutra", "variant", "partial", "absent"]
    source_class: str | None = None
    segments: list[ClaimSegment] = []
