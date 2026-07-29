"""Citation whitelist enforcement.

Background — every assistant answer flows through this guard before being
streamed to the user / persisted to ``chat_messages``. The LLM's system
prompt forbids citing texts that aren't in the retrieved context, but
"forbidden" is not "prevented": when the model slips, the user sees a
plausible-looking ``【《伪造经名》第N卷】`` reference, which is the single
worst failure mode for a scholarly tool. This module is the deterministic
backstop after the prompt's moral one.

Two failure modes are caught:

1. **Hallucinated title** — ``【《X》第N卷】`` where ``X`` does not appear
   in the retrieved sources or their aligned parallels. Rewritten to plain
   prose ``《X》`` — the clickable 【】 wrapper is stripped (so the user can
   never click through to an empty sidebar), but no inline warning is
   injected. An un-retrieved title becoming a bare ``《X》`` mention is exactly
   the prose fallback the system prompt already asks for; an inline
   "（未验证）" scold mid-sentence/mid-table only disfigured otherwise-correct
   answers (the LLM routinely names real canonical texts that retrieval — which
   favours dense commentaries over base sutras — simply didn't surface). The
   mutation is still logged for drift monitoring.

2. **Wrong fascicle** — title ``X`` is in the whitelist but ``N`` does
   not match any source's ``juan_num`` for that title. Rewritten to use
   the closest matching source's actual fascicle number, so the citation
   link the frontend generates points at a real fascicle of the real
   text instead of a 404.

The whitelist is the union of the primary RAG hits' (title_zh, juan_num)
pairs and every aligned ``parallel_chunks[]`` (title, juan_num) — when
the LLM legitimately cites a Pali / Tibetan parallel that arrived via
alignment_pairs, that should still count as "in the retrieved context".

Sources with ``text_id <= 0`` are excluded from the whitelist for
symmetry with the frontend's ``injectCitationLinks`` guard, which drops
them too.
"""

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass

from opencc import OpenCC

from app.core.metrics import CITATION_GUARD_MUTATIONS_TOTAL
from app.schemas.chat import ChatSource
from app.services.quote_verifier import (
    MIN_QUOTE_CHARS,
    normalise_for_match,
    preceding_quote,
)

logger = logging.getLogger(__name__)

# 繁简 fold for title matching. The LLM frequently emits a simplified 经名
# (e.g. 《地藏菩萨本愿经》) while the CBETA source title_zh is traditional
# (地藏菩薩本願經). Without folding, the whitelist check misses and a CORRECT
# citation gets stripped of its clickable 【】. quote_verifier already folds
# quotes the same way; keep the two guards symmetric.
_t2s = OpenCC("t2s")


def _norm_title(title: str) -> str:
    """Whitelist key: 繁→简 folded, stripped. Comparison-only — the answer
    keeps the LLM's original title text (the frontend's injectCitationLinks
    folds the same way, so the rendered citation still resolves)."""
    return _t2s.convert(title).strip()


# Matches 【《<title>》第<fascicle>卷】 or 【《<title>》】. The fascicle group
# is captured loosely (not just \d+) on purpose: the LLM sometimes copies
# the prompt's 【《经名》第N卷】 template verbatim and leaves a literal "N"
# in place. Capturing it lets _rewrite replace that placeholder with a real
# retrieved fascicle instead of letting "第N卷" reach the user untouched.
_CITATION_RE = re.compile(r"【《([^》]+)》(?:第([^】]+?)卷)?】")


def _parse_juan(juan_str: str | None) -> tuple[int | None, bool]:
    """Return (numeric_juan, is_placeholder).

    A digits-only token is a real fascicle number. Any other non-empty
    token — a literal "N" / "X" / "?" left unsubstituted from the prompt
    template — is a placeholder that must be replaced with a real fascicle.
    """
    if juan_str is None:
        return None, False
    if juan_str.isdigit():
        return int(juan_str), False
    return None, True


@dataclass(frozen=True)
class CitationMutation:
    """Audit record for a single rewrite. Logged for now; a future
    migration can persist these alongside chat_messages for replay."""

    kind: str  # 'unverified_title' | 'fascicle_corrected'
    original: str
    replacement: str
    title: str
    original_juan: int | None
    corrected_juan: int | None


def _build_chunk_index(sources: Iterable[ChatSource]) -> dict[str, list[tuple[int, str]]]:
    """{title -> [(juan_num, normalised chunk_text), ...]} for quote lookup.

    Parallels are included on the same footing as primary hits, mirroring
    ``_build_whitelist`` — a legitimately cited Pali/Tibetan parallel must be
    able to anchor its own fascicle too.
    """
    idx: dict[str, list[tuple[int, str]]] = {}
    for s in sources:
        if s.text_id <= 0 or not s.title_zh:
            continue
        idx.setdefault(_norm_title(s.title_zh), []).append(
            (s.juan_num, normalise_for_match(s.chunk_text or ""))
        )
        for p in s.parallel_chunks:
            if p.text_id <= 0 or not p.title:
                continue
            idx.setdefault(_norm_title(p.title), []).append(
                (p.juan_num, normalise_for_match(p.chunk_text or ""))
            )
    return idx


def _juan_holding_quote(
    chunk_index: dict[str, list[tuple[int, str]]], norm_title: str, quote: str | None
) -> int | None:
    """The fascicle whose retrieved chunk contains ``quote`` verbatim, if one does.

    This is the whole point of the quote-aware pass: ``min(valid_juans)`` is
    deterministic but arbitrary, and a citation whose fascicle was picked
    arbitrarily is a citation that sends the reader to the wrong place while
    looking checked. When the answer quotes a passage we can locate, the
    fascicle must follow the passage.

    Ambiguity is resolved by preferring the lowest juan among those that hold
    the quote, so the result stays stable across runs when a passage genuinely
    repeats across fascicles.
    """
    if not quote:
        return None
    needle = normalise_for_match(quote)
    if len(needle) < MIN_QUOTE_CHARS:
        return None
    holders = [j for j, text in chunk_index.get(norm_title, []) if needle in text]
    return min(holders) if holders else None


def _build_whitelist(sources: Iterable[ChatSource]) -> dict[str, set[int]]:
    """Build {title -> {juan_num,...}} from sources + their aligned parallels.

    A title with no associated juan_num maps to an empty set, which means
    "title is real but no fascicle was retrieved" — citations of that
    title without a fascicle pass; with a fascicle get corrected to None.
    """
    wl: dict[str, set[int]] = {}
    for s in sources:
        if s.text_id <= 0 or not s.title_zh:
            continue
        wl.setdefault(_norm_title(s.title_zh), set()).add(s.juan_num)
        for p in s.parallel_chunks:
            if p.text_id <= 0 or not p.title:
                continue
            wl.setdefault(_norm_title(p.title), set()).add(p.juan_num)
    return wl


def enforce_citation_whitelist(
    answer: str,
    sources: list[ChatSource],
) -> tuple[str, list[CitationMutation]]:
    """Rewrite citations in ``answer`` to match the source whitelist.

    Returns the corrected answer and a list of mutations the caller can
    log / persist. An answer with no 【】 references — or one whose
    citations all check out — is returned unchanged with an empty list.
    """
    if not answer or "【《" not in answer:
        return answer, []

    whitelist = _build_whitelist(sources)
    if not whitelist:
        # No usable sources at all: every 【】 reference is unverifiable.
        # Strip the brackets but keep the title so the user can still see
        # what the model meant, with a clear caveat.
        mutations: list[CitationMutation] = []

        def _strip(match: re.Match[str]) -> str:
            title = match.group(1)
            juan, _ = _parse_juan(match.group(2))
            replacement = f"《{title}》"
            mutations.append(
                CitationMutation(
                    kind="unverified_title",
                    original=match.group(0),
                    replacement=replacement,
                    title=title,
                    original_juan=juan,
                    corrected_juan=None,
                )
            )
            return replacement

        return _CITATION_RE.sub(_strip, answer), mutations

    mutations = []
    chunk_index = _build_chunk_index(sources)

    def _rewrite(match: re.Match[str]) -> str:
        original = match.group(0)
        title = match.group(1)
        original_juan, juan_is_placeholder = _parse_juan(match.group(2))

        norm_title = _norm_title(title)
        if norm_title not in whitelist:
            replacement = f"《{title}》"
            mutations.append(
                CitationMutation(
                    kind="unverified_title",
                    original=original,
                    replacement=replacement,
                    title=title,
                    original_juan=original_juan,
                    corrected_juan=None,
                )
            )
            return replacement

        valid_juans = whitelist[norm_title]
        # Title-only citation (【《X》】 with no fascicle at all) is always
        # allowed when the title is real — it points at the text as a whole.
        if original_juan is None and not juan_is_placeholder:
            return original

        # Where the quoted passage actually lives, when the answer quotes one.
        # Checked BEFORE the whitelist shortcut below: a fascicle can be
        # "retrieved" and still be the wrong one for this passage — the prod
        # case that motivated this was 俱舍論 with both 卷13 and 卷16 retrieved,
        # the quote in 16, the citation saying 13, and every guard waving it
        # through because 13 was in the whitelist.
        quote_juan = _juan_holding_quote(
            chunk_index, norm_title, preceding_quote(match.string[: match.start()])
        )
        if quote_juan is not None:
            if quote_juan == original_juan:
                return original
        elif original_juan is not None and original_juan in valid_juans:
            return original

        # Either a fascicle contradicted by the quote, one that matches no
        # source, or an unsubstituted "第N卷" placeholder. Prefer the fascicle
        # that holds the quote; fall back to the smallest retrieved one —
        # deterministic and stable across runs — or drop the fascicle entirely
        # if none was retrieved.
        if quote_juan is not None:
            corrected_juan = quote_juan
            replacement = f"【《{title}》第{corrected_juan}卷】"
        elif not valid_juans:
            replacement = f"【《{title}》】"
            corrected_juan = None
        else:
            corrected_juan = min(valid_juans)
            replacement = f"【《{title}》第{corrected_juan}卷】"

        mutations.append(
            CitationMutation(
                kind="fascicle_placeholder" if juan_is_placeholder else "fascicle_corrected",
                original=original,
                replacement=replacement,
                title=title,
                original_juan=original_juan,
                corrected_juan=corrected_juan,
            )
        )
        return replacement

    corrected = _CITATION_RE.sub(_rewrite, answer)
    return corrected, mutations


def log_mutations(
    chat_message_id: int | None,
    mutations: list[CitationMutation],
) -> None:
    """Emit one log line per mutation so a grep over backend logs can
    surface model citation drift before a database column is wired up."""
    if not mutations:
        return
    for m in mutations:
        CITATION_GUARD_MUTATIONS_TOTAL.labels(kind=m.kind).inc()
        logger.warning(
            "citation_guard %s msg_id=%s title=%r orig=%r repl=%r "
            "orig_juan=%s corrected_juan=%s",
            m.kind,
            chat_message_id,
            m.title,
            m.original,
            m.replacement,
            m.original_juan,
            m.corrected_juan,
        )
