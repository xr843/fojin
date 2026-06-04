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
- On miss we append **one consolidated caveat** at the end of the answer
  (before any ``[追问]`` block) rather than annotating each quote inline.
  The earlier per-quote inline ⚠️ markers fired so often on *correct*
  canonical quotes — retrieval favours dense commentaries over the base
  sutra that actually contains the line — that they disfigured sound answers
  mid-sentence and inside tables. The single trailing caveat keeps the
  unverified-status signal; per-quote detail still reaches the logs.

The verifier is wired *after* ``enforce_citation_whitelist`` so quotes
attached to citations the guard already stripped (unverified titles)
don't get double-flagged.
"""

import logging
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

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
_QUOTE_CITATION_RE = re.compile(
    r"[" + re.escape(_QUOTE_OPEN) + r"]"
    r"(?P<quote>.{" + str(MIN_QUOTE_CHARS) + r",400}?)"
    r"[" + re.escape(_QUOTE_CLOSE) + r"]"
    r".{0," + str(MAX_QUOTE_CITATION_GAP_CHARS) + r"}?"
    r"【《(?P<title>[^》]+)》(?:第(?P<juan>\d+)卷)?】",
    re.DOTALL,
)

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

# Marker placed at the start of the verifier's own appended caveat
# blockquote (see ``_QUOTE_CAVEAT``). If the answer is fed back through
# ``verify_quoted_content`` a second time — or a downstream pipeline
# concatenates verified answers — the blockquote scanner must skip the
# caveat itself, otherwise a real ``【《X》】`` citation that follows
# elsewhere in the answer would pair with the warning blockquote and
# emit a spurious second mutation.
_CAVEAT_BLOCK_MARKER = "⚠️ 本回答"


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


# A single, unobtrusive caveat appended once when ≥1 quote fails verification,
# replacing the previous per-quote inline ⚠️ markers. Because retrieval favours
# dense commentaries over base sutras, those inline markers fired on the LLM's
# *correct* canonical quotes (e.g. 「照见五蕴皆空」 under a 心经 commentary that
# doesn't contain the line) and disfigured otherwise-sound answers mid-sentence
# and inside tables. One caveat paragraph (placed before any [追问] block) keeps
# the scholarly signal without breaking the prose; per-quote detail still goes to
# the logs via QuoteMutation.
_QUOTE_CAVEAT = "> ⚠️ 本回答中部分直接引文未能在检索到的经文片段中逐字核实，建议点按引用链接核对原文。"


def _append_caveat(answer: str) -> str:
    """Insert the quote caveat as its own paragraph, before any trailing
    ``[追问]`` suggestion lines so it reads as part of the answer body rather
    than after the follow-up buttons (which the frontend renders separately and
    the backend strips before persistence)."""
    lines = answer.split("\n")
    for i, line in enumerate(lines):
        if line.strip().startswith("[追问]"):
            head = "\n".join(lines[:i]).rstrip()
            tail = "\n".join(lines[i:])
            return f"{head}\n\n{_QUOTE_CAVEAT}\n\n{tail}"
    return answer.rstrip() + f"\n\n{_QUOTE_CAVEAT}"


def _strip_existing_caveat(answer: str) -> str:
    """Remove a previously-appended caveat blockquote so it can be re-emitted
    at the correct position below any newly-appearing fabricated content.

    Matches the canonical ``_QUOTE_CAVEAT`` line verbatim (the caveat is a
    single-line blockquote, so this is unambiguous) and trims one trailing
    blank line so we don't accumulate paragraph spacing on repeated passes.
    """
    if _QUOTE_CAVEAT not in answer:
        return answer
    return re.sub(
        r"\n*" + re.escape(_QUOTE_CAVEAT) + r"\n*",
        "\n\n",
        answer,
    ).rstrip()


def verify_quoted_content(
    answer: str, sources: list[ChatSource]
) -> tuple[str, list[QuoteMutation]]:
    """Flag quoted segments that aren't substrings of the cited source's
    chunk_text. Unchanged answers (no quote-citation pairs, or all quotes
    verified) are returned identical, with an empty mutations list.

    Implementation: regex scans for ``「…」【《X》第N卷】`` proximity pairs and
    normalises both sides. Any failing pair is recorded as a QuoteMutation
    (for logging); if there is at least one, a single consolidated caveat is
    appended once to the answer (before any ``[追问]`` block). Multiple
    failures share the one caveat rather than each getting an inline marker.
    """
    if not answer or "【《" not in answer:
        return answer, []

    mutations: list[QuoteMutation] = []

    for m in _QUOTE_CITATION_RE.finditer(answer):
        quote = m.group("quote").strip()
        title = m.group("title")
        juan_str = m.group("juan")
        juan = int(juan_str) if juan_str else None
        if len(quote) < MIN_QUOTE_CHARS:
            continue

        candidates = _find_sources(sources, title, juan)
        if not candidates:
            mutations.append(
                QuoteMutation(
                    quote=quote, title=title, juan=juan,
                    reason="no_matching_source",
                )
            )
            continue

        # Pass if the quote is a substring of ANY retrieved chunk for the
        # cited text — a multi-chunk retrieval scatters the passage across
        # several chunks of the same juan.
        normalised_quote = _normalise(quote)
        if not any(
            normalised_quote in _normalise(c.chunk_text) for c in candidates
        ):
            mutations.append(
                QuoteMutation(
                    quote=quote, title=title, juan=juan,
                    reason="quote_not_in_source",
                )
            )

    mutations.extend(_scan_blockquotes(answer, sources))

    if not mutations:
        return answer, mutations

    # Idempotent caveat: ``chat.py`` calls this verifier twice (once on
    # the streamed answer, once on the post-correction answer) and the
    # second input can carry forward a caveat the first pass appended.
    # Strip any existing caveat so the re-append lands at the bottom of
    # the current (possibly extended) answer body — this preserves the
    # single-caveat invariant while still surfacing newly-introduced
    # fabrications that appear *after* the prior caveat, which a plain
    # "skip if marker present" check would silently swallow.
    if _CAVEAT_BLOCK_MARKER in answer:
        answer = _strip_existing_caveat(answer)

    return _append_caveat(answer), mutations


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


def _scan_blockquotes(
    answer: str, sources: list[ChatSource]
) -> list[QuoteMutation]:
    """Detect ``> …`` blockquote / ``【《X》第N卷】`` pairs and verify them
    against the cited source's chunk_text with the same substring
    semantics as the inline scanner.

    Returns the list of failing mutations (empty if every blockquote
    verifies, or there are none). The caller decides whether to append
    the shared caveat — multiple blockquote failures must collapse into
    the same single caveat as the inline path, so producing inline-style
    mutations here and letting the caller pool them is the right shape.
    """
    out: list[QuoteMutation] = []
    for m in _BLOCKQUOTE_CITATION_RE.finditer(answer):
        block = m.group("block")
        quote = _strip_blockquote_markers(block)
        # Skip the verifier's own self-appended caveat blockquote so a
        # second pass over already-verified output doesn't pair the
        # warning text with an unrelated downstream citation.
        if _CAVEAT_BLOCK_MARKER in quote:
            continue
        if len(quote) < MIN_QUOTE_CHARS:
            continue

        title = m.group("title")
        juan_str = m.group("juan")
        juan = int(juan_str) if juan_str else None

        candidates = _find_sources(sources, title, juan)
        if not candidates:
            out.append(
                QuoteMutation(
                    quote=quote, title=title, juan=juan,
                    reason="blockquote_not_in_source",
                )
            )
            continue

        normalised_quote = _normalise(quote)
        if not any(
            normalised_quote in _normalise(c.chunk_text) for c in candidates
        ):
            out.append(
                QuoteMutation(
                    quote=quote, title=title, juan=juan,
                    reason="blockquote_not_in_source",
                )
            )
    return out


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
