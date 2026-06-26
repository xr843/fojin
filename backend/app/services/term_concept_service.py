"""Cross-lingual term-concept resolution + the shared IAST normalizer.

``normalize_iast`` is the single source of truth for the concept match key; both
the offline builder (scripts/build_term_concepts.py) and the ``/concept`` API
import it so they can never drift.
"""

from __future__ import annotations

import re
import unicodedata

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.dictionary import DictionaryEntry
from app.models.term_concept import TermConcept, TermConceptEntry

_NON_ALPHA = re.compile(r"[^a-z]")

# Lang display order on the concept card.
_LANG_ORDER = {"zh": 0, "sa": 1, "pi": 2, "bo": 3, "en": 4}


def normalize_iast(s: str | None) -> str:
    """Fold an IAST string to a match key: first line, de-diacritic, lowercase,
    letters-only, drop a single trailing ``m`` (accusative/anusvāra citation
    ending) so ``nirvāṇam`` and ``nirvāṇa`` both become ``nirvana``."""
    if not s:
        return ""
    head = s.strip().split("\n")[0].strip()
    decomposed = unicodedata.normalize("NFKD", head)
    ascii_ = "".join(c for c in decomposed if not unicodedata.combining(c)).lower()
    ascii_ = _NON_ALPHA.sub("", ascii_)
    return re.sub(r"m$", "", ascii_)


def _preview(definition: str | None, limit: int = 120) -> str:
    if not definition:
        return ""
    flat = " ".join(definition.split())
    return flat[:limit] + ("…" if len(flat) > limit else "")


async def resolve_concept(db: AsyncSession, q: str) -> dict:
    """Resolve a term (in any language) to its concept + linked entries grouped
    by language. Returns ``{"concept": None, "entries_by_lang": []}`` when no
    concept matches — the caller renders nothing and falls back to plain search."""
    q = (q or "").strip()
    empty = {"concept": None, "entries_by_lang": []}
    if not q:
        return empty

    # 1) exact match on a representative form, 2) fall back to the normalized key.
    concept = await db.scalar(
        select(TermConcept)
        .where(
            or_(
                TermConcept.chinese == q,
                TermConcept.sanskrit == q,
                TermConcept.pali == q,
                TermConcept.tibetan == q,
            )
        )
        .limit(1)
    )
    if concept is None:
        key = normalize_iast(q)
        if key:
            concept = await db.scalar(select(TermConcept).where(TermConcept.key == key).limit(1))
    if concept is None:
        return empty

    rows = (
        (
            await db.execute(
                select(DictionaryEntry)
                .join(TermConceptEntry, TermConceptEntry.dict_entry_id == DictionaryEntry.id)
                .options(joinedload(DictionaryEntry.source))
                .where(TermConceptEntry.concept_id == concept.id)
            )
        )
        .unique()
        .scalars()
        .all()
    )

    by_lang: dict[str, list[dict]] = {}
    for e in rows:
        by_lang.setdefault(e.lang or "other", []).append(
            {
                "id": e.id,
                "headword": (e.headword or "").split("\n")[0].strip(),
                "source_name": e.source.name_zh if e.source else None,
                "definition_preview": _preview(e.definition),
            }
        )
    entries_by_lang = [
        {"lang": lang, "entries": entries}
        for lang, entries in sorted(by_lang.items(), key=lambda kv: _LANG_ORDER.get(kv[0], 99))
    ]

    return {
        "concept": {
            "sanskrit": concept.sanskrit,
            "devanagari": concept.devanagari,
            "pali": concept.pali,
            "tibetan": concept.tibetan,
            "chinese": concept.chinese,
            "english": concept.english,
        },
        "entries_by_lang": entries_by_lang,
    }
