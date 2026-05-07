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
- On miss we **annotate inline** rather than rewrite — preserving the
  LLM's prose lets the user see what was claimed while making the
  unverified status obvious.

The verifier is wired *after* ``enforce_citation_whitelist`` so quotes
attached to citations the guard already stripped (unverified titles)
don't get double-flagged.
"""

import logging
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from app.schemas.chat import ChatSource

logger = logging.getLogger(__name__)


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
# bracketed citation. Three quote-mark families are covered:
#
#   「…」  curly Chinese quotes (most common in classical citation)
#   『…』  Chinese inner quotes (frequent in nested 引文)
#   "…"   ASCII straight quotes — LLMs that emit full-width 「」 also
#         emit ASCII " in the same answer; both must match
#
# Markdown blockquote (``> …``) is intentionally out of scope here —
# its multi-line structure needs a different scanner; if it becomes
# the dominant production form a follow-up can extend this module.
_QUOTE_CITATION_RE = re.compile(
    r"[「『\"]"
    r"(?P<quote>.{" + str(MIN_QUOTE_CHARS) + r",400}?)"
    r"[」』\"]"
    r".{0," + str(MAX_QUOTE_CITATION_GAP_CHARS) + r"}?"
    r"【《(?P<title>[^》]+)》(?:第(?P<juan>\d+)卷)?】",
    re.DOTALL,
)


# Punctuation we strip from both sides of the substring test. Includes
# CJK and ASCII forms of every mark that might survive the LLM's
# tokeniser without surviving CBETA's. Whitespace handled separately.
_STRIP_PUNCT_RE = re.compile(
    r"[\s,.!?;:\"'\(\)\[\]\-_~`<>"
    r"，。！？、；：「」『』\"\"''《》〈〉…—（）\[\]【】·•～　]+"
)


@dataclass(frozen=True)
class QuoteMutation:
    """Audit record for a single quote that failed verification."""

    quote: str
    title: str
    juan: int | None
    reason: str  # 'no_matching_source' | 'quote_not_in_source'


def _normalise(s: str) -> str:
    """Aggressive normalisation for the substring test.

    Goals:
      1. NFKC fold so half/full-width forms compare equal
      2. Strip every punctuation and whitespace character so that an
         LLM that drops a comma doesn't false-positive
      3. Lowercase (no effect on CJK but covers stray Latin)

    What this does *not* do: 简→繁 conversion. The cited source is
    already traditional (CBETA stores 繁 only); if the LLM emits 简
    inside its own quote it deserves to fail verification — quoting
    a canonical text in 简 isn't preserving the citation either.
    """
    s = unicodedata.normalize("NFKC", s)
    s = _STRIP_PUNCT_RE.sub("", s)
    return s.lower()


def _find_source(
    sources: Iterable[ChatSource], title: str, juan: int | None
) -> ChatSource | None:
    """Locate the source whose ``title_zh`` and ``juan_num`` match.

    Falls back to title-only match (any juan) when the user-supplied
    juan can't be found — the verifier's job is to check the quote
    against *some* legitimate retrieval of that text, and the LLM
    occasionally cites the right text with a slightly off fascicle
    number that the citation guard already corrected.
    """
    title_match: ChatSource | None = None
    parallel_title_match: ChatSource | None = None
    for s in sources:
        if s.title_zh == title:
            if juan is not None and s.juan_num == juan:
                return s
            if title_match is None:
                title_match = s
        # Always check parallels — a Pali / Tibetan parallel arrives
        # via alignment_pairs as a child of an unrelated lzh source,
        # so the parent's title_zh is never the parallel's title.
        for p in s.parallel_chunks:
            if p.title != title:
                continue
            if juan is None or p.juan_num == juan:
                # Adapt the parallel chunk into a ChatSource-shaped
                # carrier so the substring test reads its chunk_text.
                return ChatSource(
                    text_id=p.text_id,
                    juan_num=p.juan_num,
                    chunk_index=p.chunk_index,
                    chunk_text=p.chunk_text,
                    score=1.0,
                    title_zh=p.title,
                    lang=p.lang,
                )
            if parallel_title_match is None:
                parallel_title_match = ChatSource(
                    text_id=p.text_id, juan_num=p.juan_num,
                    chunk_index=p.chunk_index, chunk_text=p.chunk_text,
                    score=1.0, title_zh=p.title, lang=p.lang,
                )
    return title_match or parallel_title_match


def verify_quoted_content(
    answer: str, sources: list[ChatSource]
) -> tuple[str, list[QuoteMutation]]:
    """Annotate quoted segments that aren't substrings of the cited
    source's chunk_text. Unchanged answers (no quote-citation pairs,
    or all quotes verified) are returned identical, with empty
    mutations list.

    Implementation: regex scans for ``「…」【《X》第N卷】`` proximity
    pairs, normalises both sides, and inserts an inline ⚠️ marker
    after any failing pair. Multiple failing pairs in one answer get
    individual annotations.
    """
    if not answer or "【《" not in answer:
        return answer, []

    mutations: list[QuoteMutation] = []
    annotations: list[tuple[int, str]] = []  # (insert_at_index, marker)

    for m in _QUOTE_CITATION_RE.finditer(answer):
        quote = m.group("quote").strip()
        title = m.group("title")
        juan_str = m.group("juan")
        juan = int(juan_str) if juan_str else None
        if len(quote) < MIN_QUOTE_CHARS:
            continue

        source = _find_source(sources, title, juan)
        if source is None:
            mutations.append(
                QuoteMutation(
                    quote=quote, title=title, juan=juan,
                    reason="no_matching_source",
                )
            )
            annotations.append(
                (m.end(), "[⚠️ 引文出处未在检索结果中找到]")
            )
            continue

        normalised_quote = _normalise(quote)
        normalised_source = _normalise(source.chunk_text)
        if normalised_quote not in normalised_source:
            mutations.append(
                QuoteMutation(
                    quote=quote, title=title, juan=juan,
                    reason="quote_not_in_source",
                )
            )
            annotations.append(
                (m.end(), "[⚠️ 引文未在该卷原文中验证到，请谨慎引用]")
            )

    if not annotations:
        return answer, mutations

    # Insert markers from right-to-left so earlier indices stay valid.
    annotated = answer
    for index, marker in sorted(annotations, key=lambda x: x[0], reverse=True):
        annotated = annotated[:index] + marker + annotated[index:]
    return annotated, mutations


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
