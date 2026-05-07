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
   in the retrieved sources or their aligned parallels. Rewritten to
   ``《X》（未在检索结果中验证，请谨慎）`` so the user keeps the model's
   intent but loses the false air of authority a 【】 reference carries.

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

from app.schemas.chat import ChatSource

logger = logging.getLogger(__name__)


# Matches 【《<title>》第<digits>卷】 or 【《<title>》】.
# Mirrors the frontend regex in ReaderAIPanel.tsx#injectCitationLinks so a
# citation that survives this guard is exactly the citation the frontend
# will rewrite into a clickable link.
_CITATION_RE = re.compile(r"【《([^》]+)》(?:第(\d+)卷)?】")


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
        wl.setdefault(s.title_zh, set()).add(s.juan_num)
        for p in s.parallel_chunks:
            if p.text_id <= 0 or not p.title:
                continue
            wl.setdefault(p.title, set()).add(p.juan_num)
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
            juan_str = match.group(2)
            juan = int(juan_str) if juan_str else None
            replacement = f"《{title}》（未在检索结果中验证，请谨慎）"
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

    def _rewrite(match: re.Match[str]) -> str:
        original = match.group(0)
        title = match.group(1)
        juan_str = match.group(2)
        original_juan = int(juan_str) if juan_str else None

        if title not in whitelist:
            replacement = f"《{title}》（未在检索结果中验证，请谨慎）"
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

        valid_juans = whitelist[title]
        # Title-only citation (【《X》】 with no fascicle) is always allowed
        # when the title is real — it points at the text as a whole.
        if original_juan is None:
            return original
        if original_juan in valid_juans:
            return original

        # Title is real, fascicle is wrong. Pick the smallest retrieved
        # fascicle as the deterministic replacement — picking any one is
        # better than picking none, and "smallest" is stable across runs.
        if not valid_juans:
            # Title was retrieved but with no fascicle context. Drop the
            # fascicle from the citation rather than invent one.
            replacement = f"【《{title}》】"
            corrected_juan = None
        else:
            corrected_juan = min(valid_juans)
            replacement = f"【《{title}》第{corrected_juan}卷】"

        mutations.append(
            CitationMutation(
                kind="fascicle_corrected",
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
