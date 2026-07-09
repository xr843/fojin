"""Quoted-content verification for LLM answers.

The citation guard catches one class of hallucination: an answer that
wraps a fabricated reference in ``【《X》第N卷】`` form. This module
catches the other class: an answer whose ``【…】`` reference is real
but whose **quoted passage** before it is invented.

Production sample (2026-05-07): an answer correctly cited
``【《大般若经》第600卷】`` (which the guard then rejected because the
title wasn't retrieved), but the same answer also offered exact-looking
``"…乃至四句偈等，为他人说，其福胜彼"`` quotes — those passages came
from the LLM's training data, not from the retrieved fascicle. A
scholarly user verifying a citation will click through, find the
reference is real, and trust the quoted text — at which point any
substring of the quote that the LLM invented becomes laundered fake
data.

The check is deliberately conservative:

- We only verify quotes immediately attached to a ``【《X》第N卷】``
  reference (within ``MAX_QUOTE_CITATION_GAP_CHARS``). A loose mention
  of a passage somewhere else in the answer isn't bound to a specific
  source and so isn't checkable.
- We require the quoted segment to be at least ``MIN_QUOTE_CHARS``
  long. Short fragments produce too much normalisation noise (LLMs
  paraphrase short passages constantly).
- We normalise (NFKC fold + whitespace + punctuation strip) before
  the substring test. Anything that survives this and is still missing
  from the cited chunk's text is almost certainly invented, not
  paraphrased. We deliberately do **not** apply 简→繁 here: the cited
  source is canonical traditional, and an LLM that emits a 简-script
  quote inside a 繁-script source citation has already lost the
  attribution chain it claimed to preserve, so failing the check is
  the correct behaviour.
- On miss we **downgrade** the quote: strip its open/close marks (or the
  ``> `` blockquote prefix) so the passage reads as the model's own prose,
  still followed by its citation. fojin thus never *serves* a false verbatim
  quote — the earlier design only appended a caveat and left the misquote in
  place. Each downgrade is recorded as a ``QuoteMutation`` for telemetry (how
  often the model paraphrases-as-quote is a model-quality signal), and the
  trust status marks the answer ``quote_relaxed`` (a correction tier, not a
  warning) rather than ``quote_unverified``. The measured-but-useless prompt
  approach (PR #901) is why this is done deterministically instead.

The verifier is wired *after* ``enforce_citation_whitelist`` so quotes
attached to citations the guard already stripped (unverified titles)
don't get double-flagged.
"""

import logging
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from difflib import SequenceMatcher

from opencc import OpenCC

from app.schemas.chat import ChatSource

logger = logging.getLogger(__name__)

# 繁→简 fold for the substring test. The user asks in 简体 and the LLM
# answers — and quotes — in 简体, while CBETA stores 繁体. Rendering a quote
# in the reader's script is localisation, not a fidelity loss, so a script
# mismatch must not by itself fail verification.
_t2s = OpenCC("t2s")


# Minimum length of a quoted segment we'll subject to verification.
# Below this, paraphrase noise dominates and false positives explode —
# LLMs routinely shorten "色不异空，空不异色" to "色不异空" and we don't
# want to flag that.
MIN_QUOTE_CHARS = 12

# Fuzzy-classification of a FAILED quote (measurement only — never changes
# the served answer). A failed quote whose best windowed similarity to the
# cited chunk is >= this is bucketed "near_miss" (almost verbatim: a variant
# character, edition/punctuation difference, or a correct quote the retriever
# didn't surface — i.e. likely-correct text the downgrade wrongly strips);
# below it is "absent" (a paraphrase or fabrication). 0.85 keeps 1–2 differing
# chars in a ~12-char quote on the near_miss side while excluding paraphrases.
NEAR_MISS_THRESHOLD = 0.85

# Cap on how many sliding windows _windowed_ratio evaluates, so a
# pathologically long chunk can't make failure-classification quadratic.
_MAX_RATIO_WINDOWS = 256

# Maximum distance (chars) between the closing quote and the start of
# the trailing 【《X》第N卷】 reference for them to count as bound. A
# user inserting two sentences of commentary between quote and
# citation would push the pair past this threshold and we'd skip
# verification — preferring under-verification to misattribution.
MAX_QUOTE_CITATION_GAP_CHARS = 80

# Match a CJK quote-mark pair followed within the gap window by a
# bracketed citation. Five quote-mark families are covered:
#
#   「…」    Chinese L-brackets (most common in 古典 引文)
#   『…』    Chinese double L-brackets (nested 引文)
#   “…”     Typographic curly double quotes (U+201C / U+201D) —
#             Markdown-rendered LLM output uses these by default
#   ‘…’     Typographic curly single quotes (U+2018 / U+2019)
#   "…"     ASCII straight quotes (LLMs occasionally emit these in
#             code-fenced / programmatic content)
#
# Production sample 2026-05-07 showed DeepSeek answers using U+201C /
# U+201D exclusively for inline quotes — an earlier scanner that only
# matched 「」 + ASCII `"` was silent on every production
# hallucination, defeating the entire module. Adding the curly forms
# is the fix.
#
# Markdown blockquote (``> …``) gets a dedicated multi-line scanner
# below — it needs different framing because the body is never wrapped
# in 「」/“”/'' and may span several lines.
_QUOTE_OPEN = "「『“‘\""
_QUOTE_CLOSE = "」』”’\""
# Which close mark closes which open mark. An unpaired match (「…” ) is not a
# quotation — it is two unrelated marks the scanner happened to straddle.
_QUOTE_PAIRS = {"「": "」", "『": "』", "“": "”", "‘": "’", '"': '"'}

# A quote body runs to the **first** mark that closes its own opener, and never
# across a line break. Both bounds are load-bearing, and both were missing:
#
# - Unbounded by its closing mark, the lazy body walked *past* it to whichever
#   later mark happened to sit within the gap window of a citation. CJK prose
#   uses 「」 for emphasis constantly (「念」「寻」), so an answer that emphasised
#   two terms and cited a source three lines down had the entire span between
#   them captured as one "quote" and then downgraded as fabricated.
# - Unbounded by the line, that walk crossed paragraphs, swallowing bullet
#   lists and markdown bold. Blockquotes are a separate multi-line construct
#   with their own scanner below; an inline quote is single-line.
#
# Prod diagnostics 2026-07-09 (chat_answer_diagnostics): 69% of the quotes
# bucketed ``absent`` contained a newline and 45% contained ``**``, mean length
# 145 chars — against 36 chars and zero newlines for the ``near_miss`` (real)
# ones. The verifier was mostly measuring itself.
#
# Only the *paired* mark terminates the body. Excluding every close mark from
# every body would trade over-capture for under-verification: U+2019 is both a
# closing single quote and the English apostrophe, so “the Buddha’s words” would
# stop being checked at all.
_QUOTE_PAIRS = {"「": "」", "『": "』", "“": "”", "‘": "’", '"': '"'}

# Groups capture every part so a failing quote can be *downgraded* — rebuilt as
# ``quote + gap + cite`` with the open/close marks dropped, turning a false
# verbatim quote into honest prose that still cites the source. One alternation
# branch per mark family, since stdlib ``re`` forbids reusing a group name and
# cannot backreference across two different characters.
_QUOTE_CITATION_RE = re.compile(
    r"(?:"
    + r"|".join(
        r"(?P<open" + str(i) + r">" + re.escape(o) + r")"
        r"(?P<quote" + str(i) + r">[^\n" + re.escape(c) + r"]"
        r"{" + str(MIN_QUOTE_CHARS) + r",400})"
        + re.escape(c)
        for i, (o, c) in enumerate(_QUOTE_PAIRS.items())
    )
    + r")"
    r"(?P<gap>[^\n]{0," + str(MAX_QUOTE_CITATION_GAP_CHARS) + r"}?)"
    r"(?P<cite>【《(?P<title>[^》]+)》(?:第(?P<juan>\d+)卷)?】)",
)


def _matched_quote(m: re.Match[str]) -> str:
    """The body of whichever mark-family branch matched."""
    for i in range(len(_QUOTE_PAIRS)):
        q = m.group("quote" + str(i))
        if q is not None:
            return q
    raise AssertionError("no quote branch matched")  # pragma: no cover

# Match a contiguous Markdown blockquote block followed (within the
# usual gap window of subsequent non-blockquote text) by a
# ``【《X》第N卷】`` citation. The blockquote body is captured in full so
# we can strip the per-line ``> `` markers before substring testing.
#
# Two citation positions are both LLM-natural and both supported:
#   1. inline on the final ``> `` line:
#         > 引文内容
#         > ——【《心經》第1卷】
#   2. as a sibling paragraph after the block:
#         > 引文内容
#
#         【《心經》第1卷】
#
# A multi-paragraph gap (commentary in between) is intentionally too
# long to match — same under-verification stance as the inline path.
_BLOCKQUOTE_CITATION_RE = re.compile(
    r"(?P<block>(?:^>[^\n]*(?:\n|$))+)"
    r"(?P<gap>(?:[^\n]*\n){0,2}[^\n]{0," + str(MAX_QUOTE_CITATION_GAP_CHARS) + r"}?)"
    r"【《(?P<title>[^》]+)》(?:第(?P<juan>\d+)卷)?】",
    re.MULTILINE,
)


# Punctuation we strip from both sides of the substring test. Includes
# CJK and ASCII forms of every mark that might survive the LLM's
# tokeniser without surviving CBETA's. Whitespace handled separately.
_STRIP_PUNCT_RE = re.compile(
    r"[\s,.!?;:\"'\(\)\[\]\-_~`<>*"
    r"，。！？、；：「」『』“”‘’《》〈〉…—（）\[\]【】·•～　]+"
)


@dataclass(frozen=True)
class QuoteMutation:
    """Audit record for a single quote that failed verification."""

    quote: str
    title: str
    juan: int | None
    # 'no_matching_source' | 'quote_not_in_source' | 'blockquote_not_in_source'
    # The blockquote variant exists so the audit trail distinguishes
    # inline-paraphrase vs long-form-fabrication failure modes, which
    # have different LLM root causes and different downstream prompt
    # mitigations.
    reason: str
    # Fuzzy-match telemetry for the failed quote (measurement only — does NOT
    # affect the served answer). ``similarity`` is the best windowed
    # SequenceMatcher ratio of the normalised quote against the cited chunk
    # (0.0 when the cite matched no retrieved chunk). ``bucket`` is
    # "near_miss" (>= NEAR_MISS_THRESHOLD — a likely-correct quote the
    # retriever missed) or "absent" (paraphrase / fabrication). Defaulted so
    # every existing construction site and consumer stays valid.
    similarity: float = 0.0
    bucket: str = "absent"


def _normalise(s: str) -> str:
    """Aggressive normalisation for the substring test.

    Goals:
      1. NFKC fold so half/full-width forms compare equal
      2. 繁→简 fold so a simplified-Chinese quote matches a traditional
         CBETA source — without this every quote in a 简体 answer of a
         繁体 source false-fails, drowning the answer in ⚠️ notices
      3. Strip every punctuation and whitespace character so that an
         LLM that drops a comma doesn't false-positive
      4. Lowercase (no effect on CJK but covers stray Latin)
    """
    s = unicodedata.normalize("NFKC", s)
    s = _t2s.convert(s)
    s = _STRIP_PUNCT_RE.sub("", s)
    return s.lower()


def _find_sources(
    sources: Iterable[ChatSource], title: str, juan: int | None
) -> list[ChatSource]:
    """All retrieved chunks (and parallels) whose title/juan match the cite.

    RAG returns several chunks per text, and the quoted sentence is often
    not in the first-iterated one — so the verifier must check the quote
    against the *whole* candidate set, not a single hit. Returning the first
    match (as the earlier ``_find_source`` did) false-flagged a legitimate
    quote whenever it landed in a non-first retrieved chunk of the cited juan.

    Exact (title + juan) matches are returned when juan is given; if none
    match the juan, falls back to every title match (any juan) — the
    citation guard occasionally corrects a slightly-off fascicle number.

    Title comparison is 繁→简 folded: the LLM may write the title in 简体
    while CBETA stores it in 繁体, and an exact ``==`` would then miss the
    source and false-flag the quote as having no matching source.
    """
    target_title = _t2s.convert(title)
    exact: list[ChatSource] = []
    title_only: list[ChatSource] = []
    for s in sources:
        if s.title_zh and _t2s.convert(s.title_zh) == target_title:
            if juan is not None and s.juan_num == juan:
                exact.append(s)
            else:
                title_only.append(s)
        # Always check parallels — a Pali / Tibetan parallel arrives
        # via alignment_pairs as a child of an unrelated lzh source,
        # so the parent's title_zh is never the parallel's title.
        for p in s.parallel_chunks:
            if not p.title or _t2s.convert(p.title) != target_title:
                continue
            # Adapt the parallel chunk into a ChatSource-shaped carrier
            # so the substring test reads its chunk_text.
            carrier = ChatSource(
                text_id=p.text_id,
                juan_num=p.juan_num,
                chunk_index=p.chunk_index,
                chunk_text=p.chunk_text,
                score=1.0,
                title_zh=p.title,
                lang=p.lang,
            )
            if juan is None or p.juan_num == juan:
                exact.append(carrier)
            else:
                title_only.append(carrier)
    return exact or title_only


def _quote_failure_reason(
    quote: str, title: str, juan: int | None, sources: list[ChatSource], *, blockquote: bool
) -> str | None:
    """Return a failure reason if ``quote`` is not verbatim in the cited source,
    else None (verified). Same detection as before — only the *action* changed
    from flag-and-caveat to downgrade."""
    candidates = _find_sources(sources, title, juan)
    if not candidates:
        return "blockquote_not_in_source" if blockquote else "no_matching_source"
    normalised = _normalise(quote)
    if any(normalised in _normalise(c.chunk_text) for c in candidates):
        return None
    return "blockquote_not_in_source" if blockquote else "quote_not_in_source"


def _windowed_ratio(needle: str, haystack: str) -> float:
    """Best ``SequenceMatcher`` ratio of ``needle`` against any same-length
    window of ``haystack``. Windowing stops a short quote's score from being
    diluted by a long (~500-char) chunk. Both inputs must already be
    ``_normalise``d. Coarse step + a window cap keep it O(reasonable); the
    tail window is always included so a match at the very end isn't missed."""
    if not needle or not haystack:
        return 0.0
    nlen = len(needle)
    if len(haystack) <= nlen:
        return SequenceMatcher(None, needle, haystack, autojunk=False).ratio()
    step = max(1, nlen // 4)
    starts = list(range(0, len(haystack) - nlen + 1, step))
    tail = len(haystack) - nlen
    if starts[-1] != tail:
        starts.append(tail)
    if len(starts) > _MAX_RATIO_WINDOWS:
        # Evenly subsample to bound cost on pathologically long chunks.
        stride = len(starts) / _MAX_RATIO_WINDOWS
        starts = [starts[int(i * stride)] for i in range(_MAX_RATIO_WINDOWS)]
    best = 0.0
    for s in starts:
        r = SequenceMatcher(None, needle, haystack[s : s + nlen], autojunk=False).ratio()
        if r > best:
            best = r
            if best >= 0.999:
                break
    return best


def _classify_failure(
    quote: str, title: str, juan: int | None, sources: list[ChatSource]
) -> tuple[float, str]:
    """Best fuzzy similarity + bucket for a quote that already FAILED the
    verbatim substring test. Measurement only — never changes the answer.

    ``similarity`` is the max windowed ratio of the normalised quote against
    any candidate chunk of the cited text (0.0 when the cite matched no
    retrieved chunk at all). ``bucket`` splits the two very different failure
    modes that a flat verified_rate conflates:
      * ``near_miss`` (>= ``NEAR_MISS_THRESHOLD``): almost verbatim — a variant
        character, an edition/punctuation difference, or a correct quote whose
        source chunk the retriever didn't surface. A likely-correct quote the
        downgrade wrongly strips.
      * ``absent``: nowhere near the source — a paraphrase or fabrication.
    """
    candidates = _find_sources(sources, title, juan)
    if not candidates:
        return 0.0, "absent"
    nq = _normalise(quote)
    similarity = max(
        (_windowed_ratio(nq, _normalise(c.chunk_text)) for c in candidates),
        default=0.0,
    )
    bucket = "near_miss" if similarity >= NEAR_MISS_THRESHOLD else "absent"
    return similarity, bucket


def verify_quoted_content(
    answer: str, sources: list[ChatSource]
) -> tuple[str, list[QuoteMutation]]:
    """Downgrade quoted segments that aren't verbatim in the cited source.

    Detection is unchanged (a ``「…」【《X》第N卷】`` / blockquote pair whose quote
    isn't a substring of any retrieved chunk of the cited text, 繁→简 folded).
    The *action* is now deterministic: instead of appending a caveat, the quote
    marks are stripped so the passage reads as the model's own prose while still
    citing the source — fojin never *serves* a false verbatim quote. Each
    downgrade is recorded as a ``QuoteMutation`` for telemetry.

    Returns ``(corrected_answer, mutations)``; an answer with no failing quotes
    is returned identical with an empty list. Idempotent: a downgraded passage
    carries no quote marks, so a second pass is a no-op (and returns no
    mutations — the served answer is already clean)."""
    if not answer or "【《" not in answer:
        return answer, []

    mutations: list[QuoteMutation] = []

    def _downgrade_inline(m: re.Match[str]) -> str:
        quote = _matched_quote(m).strip()
        if len(quote) < MIN_QUOTE_CHARS:
            return m.group(0)
        title = m.group("title")
        juan = int(m.group("juan")) if m.group("juan") else None
        reason = _quote_failure_reason(quote, title, juan, sources, blockquote=False)
        if reason is None:
            return m.group(0)
        similarity, bucket = _classify_failure(quote, title, juan, sources)
        mutations.append(QuoteMutation(
            quote=quote, title=title, juan=juan, reason=reason,
            similarity=similarity, bucket=bucket,
        ))
        # Drop the open/close marks: keep the text (now prose) + gap + citation.
        return _matched_quote(m) + m.group("gap") + m.group("cite")

    corrected = _QUOTE_CITATION_RE.sub(_downgrade_inline, answer)
    corrected = _downgrade_blockquotes(corrected, sources, mutations)
    if mutations:
        near_miss = sum(1 for m in mutations if m.bucket == "near_miss")
        absent = len(mutations) - near_miss
        # One structured line per answer so a `grep quote_verify` over logs
        # shows how much of the (post-downgrade) "unverified" volume is
        # likely-correct near-misses vs. real paraphrase/fabrication —
        # i.e. how much of the low verified_rate is a measurement artifact.
        logger.info(
            "quote_verify buckets: near_miss=%d absent=%d total_failed=%d",
            near_miss, absent, len(mutations),
        )
    return corrected, mutations


def _strip_blockquote_markers(block: str) -> str:
    """Strip the per-line ``> `` Markdown prefix from a blockquote so we
    can hand the joined body to the substring test.

    Blank ``>`` lines (used by LLMs as paragraph breaks inside a single
    quotation) are dropped — they carry no content and otherwise leave
    stray ``\\n\\n`` runs that survive normalisation noise checks.
    """
    out_lines: list[str] = []
    for raw in block.splitlines():
        # Tolerate up to one leading whitespace before ``>`` and the
        # standard ``> `` / ``>`` (no space) forms.
        s = raw.lstrip()
        if not s.startswith(">"):
            # Defensive — _BLOCKQUOTE_CITATION_RE only captures `>`-led
            # lines, so this branch shouldn't fire in normal use.
            continue
        s = s[1:].lstrip(" ")
        if s:
            out_lines.append(s)
    return " ".join(out_lines).strip()


def _downgrade_blockquotes(
    answer: str, sources: list[ChatSource], mutations: list[QuoteMutation]
) -> str:
    """Downgrade ``> …`` blockquote / ``【《X》第N卷】`` pairs whose quote isn't
    verbatim in the cited source: strip the per-line ``> `` markers so the block
    becomes an ordinary paragraph (still followed by its citation). Appends a
    QuoteMutation per downgrade to ``mutations``.

    Same substring detection as the inline path. A verifying blockquote is left
    untouched. Idempotent: a downgraded block no longer starts with ``>``, so a
    second pass doesn't match it."""
    def _sub(m: re.Match[str]) -> str:
        block = m.group("block")
        quote = _strip_blockquote_markers(block)
        if len(quote) < MIN_QUOTE_CHARS:
            return m.group(0)
        title = m.group("title")
        juan = int(m.group("juan")) if m.group("juan") else None
        reason = _quote_failure_reason(quote, title, juan, sources, blockquote=True)
        if reason is None:
            return m.group(0)
        similarity, bucket = _classify_failure(quote, title, juan, sources)
        mutations.append(QuoteMutation(
            quote=quote, title=title, juan=juan, reason=reason,
            similarity=similarity, bucket=bucket,
        ))
        # Replace the blockquote body with its unmarked prose; keep everything
        # after the block (gap + citation) exactly as matched.
        return quote + "\n\n" + m.group(0)[len(block):]

    return _BLOCKQUOTE_CITATION_RE.sub(_sub, answer)


def log_quote_mutations(
    chat_message_id: int | None,
    mutations: list[QuoteMutation],
) -> None:
    """One log line per failed quote so a future ``grep
    quote_verifier`` over backend logs surfaces volume + shape before
    a database column is wired up."""
    for m in mutations:
        logger.warning(
            "quote_verifier %s msg_id=%s title=%r juan=%s "
            "quote_len=%d quote_head=%r",
            m.reason,
            chat_message_id,
            m.title,
            m.juan,
            len(m.quote),
            m.quote[:40],
        )
