"""Build the cross-lingual term-concept layer (Phase 1, structured backbone).

Populates ``term_concepts`` + ``term_concept_entries`` from the structured
concordance dictionaries that pair languages *inside one entry*:

  - 翻譯名義大集 (``dila-mvp``): headword = Sanskrit IAST + Devanagari; the
    definition repeats those and adds Chinese form(s) + Tibetan (Wylie + script).
  - 四譯合璧輯要 (``siyi-hebi``): definition tags 【梵】【漢】【藏】【巴】【滿】【蒙】.

then joins the rest of the corpus by normalized romanized headword:

  - Any Sanskrit / Pali entry whose normalized headword matches an existing
    concept key is linked (and fills the concept's pali/sanskrit display form).
  - Any Chinese entry whose headword equals a concept's representative Chinese
    form is linked.

Concepts are seeded ONLY from the bridge dicts, never from MW/DPD/… — a concept
must have a Chinese anchor to be useful on the (Chinese-user-facing) concept card.
This keeps Phase 1 high-precision; the noisy "extract romanization from Chinese
definitions" layer is deferred to Phase 2.

The build is a full rebuild (wipes both tables first) so re-runs are
deterministic and idempotent. It only writes the two new tables.

Run inside the backend container where the corpus DB is reachable:
    docker compose exec -T backend python -m scripts.build_term_concepts
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models import DataSource, DictionaryEntry, TermConcept, TermConceptEntry
from app.services.term_concept_service import normalize_iast

logger = logging.getLogger(__name__)

# Source codes whose entries pack all languages into one row.
MVP_CODE = "dila-mvp"
SIYI_CODE = "siyi-hebi"

# ─────────────────────────── pure functions (unit-tested) ───────────────────


def classify_script(seg: str) -> str:
    """Script of the first strong character: devanagari / tibetan / han / latin / other."""
    for ch in seg:
        o = ord(ch)
        if 0x0900 <= o <= 0x097F:
            return "devanagari"
        if 0x0F00 <= o <= 0x0FFF:
            return "tibetan"
        if 0x3400 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF:
            return "han"
        if "a" <= ch.lower() <= "z":
            return "latin"
    return "other"


def parse_mvp_entry(headword: str | None, definition: str | None) -> dict:
    """Extract {sanskrit, devanagari, chinese[list], tibetan} from a Mahāvyutpatti
    entry. Buckets segments by Unicode script rather than position, so the
    dictionary's irregular nesting does not break parsing."""
    res: dict = {"sanskrit": None, "devanagari": None, "chinese": [], "tibetan": None}
    for line in (headword or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        sc = classify_script(line)
        if sc == "latin" and res["sanskrit"] is None:
            res["sanskrit"] = line
        elif sc == "devanagari" and res["devanagari"] is None:
            res["devanagari"] = line
    for line in (definition or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        sc = classify_script(line)
        if sc == "han":
            if line not in res["chinese"]:
                res["chinese"].append(line)
        elif sc == "tibetan" and res["tibetan"] is None:
            res["tibetan"] = line
        elif sc == "devanagari" and res["devanagari"] is None:
            res["devanagari"] = line
        elif sc == "latin" and res["sanskrit"] is None:
            res["sanskrit"] = line
    return res


_SIYI_TAG = re.compile(r"【(.)】\s*([^【]*)")
_SIYI_MAP = {
    "梵": "sanskrit",
    "漢": "chinese",
    "藏": "tibetan",
    "巴": "pali",
}


def parse_siyi_definition(definition: str | None) -> dict:
    """Extract {sanskrit, chinese, tibetan, pali} from 四譯合璧 【x】-tagged defs.
    Manchu/Mongolian tags exist but Phase 1 keeps only the four core languages."""
    res: dict = {}
    for m in _SIYI_TAG.finditer(definition or ""):
        field = _SIYI_MAP.get(m.group(1))
        val = m.group(2).strip()
        if field and val and field not in res:
            res[field] = val
    return res


# ─────────────────────────── DB build ───────────────────────────────────────


async def _source_id(session, code: str) -> int | None:
    return await session.scalar(select(DataSource.id).where(DataSource.code == code))


async def build(session) -> dict:
    stats = {"concepts": 0, "links_mvp": 0, "links_siyi": 0, "links_roman": 0, "links_zh": 0}

    # Full rebuild — derived tables, safe to wipe.
    await session.execute(delete(TermConceptEntry))
    await session.execute(delete(TermConcept))
    await session.flush()

    mvp_id = await _source_id(session, MVP_CODE)
    siyi_id = await _source_id(session, SIYI_CODE)
    if mvp_id is None:
        logger.warning("source %r not found — concept backbone will be empty", MVP_CODE)
    if siyi_id is None:
        logger.warning("source %r not found — skipping 四譯合璧 enrichment", SIYI_CODE)

    concepts: dict[str, TermConcept] = {}  # key -> concept
    links: set[tuple[int, int]] = set()  # (concept_id, dict_entry_id) guard

    def get_or_make(key: str) -> TermConcept | None:
        if not key:
            return None
        c = concepts.get(key)
        if c is None:
            c = TermConcept(key=key)
            session.add(c)
            concepts[key] = c
        return c

    async def link(concept: TermConcept, entry_id: int, lang: str, method: str, conf: str = "high"):
        # concept.id may be None until flush; flush lazily when we need ids.
        if concept.id is None:
            await session.flush()
        pair = (concept.id, entry_id)
        if pair in links:
            return False
        links.add(pair)
        session.add(
            TermConceptEntry(
                concept_id=concept.id, dict_entry_id=entry_id, lang=lang, method=method, confidence=conf
            )
        )
        return True

    # Phase 1 — Mahāvyutpatti: seed concepts (sa + zh + bo).
    if mvp_id:
        rows = (
            await session.execute(
                select(DictionaryEntry).where(DictionaryEntry.source_id == mvp_id)
            )
        ).scalars()
        for e in rows:
            p = parse_mvp_entry(e.headword, e.definition)
            key = normalize_iast(p["sanskrit"])
            c = get_or_make(key)
            if c is None:
                continue
            c.sanskrit = c.sanskrit or p["sanskrit"]
            c.devanagari = c.devanagari or p["devanagari"]
            c.tibetan = c.tibetan or p["tibetan"]
            if not c.chinese and p["chinese"]:
                c.chinese = p["chinese"][0]
            if await link(c, e.id, e.lang or "sa", "mvp"):
                stats["links_mvp"] += 1

    # Phase 2 — 四譯合璧: enrich + link by Sanskrit key.
    if siyi_id:
        rows = (
            await session.execute(
                select(DictionaryEntry).where(DictionaryEntry.source_id == siyi_id)
            )
        ).scalars()
        for e in rows:
            p = parse_siyi_definition(e.definition)
            key = normalize_iast(p.get("sanskrit") or e.headword)
            c = get_or_make(key)
            if c is None:
                continue
            c.sanskrit = c.sanskrit or p.get("sanskrit")
            c.chinese = c.chinese or p.get("chinese")
            c.tibetan = c.tibetan or p.get("tibetan")
            c.pali = c.pali or p.get("pali")
            if await link(c, e.id, "sa", "siyi_tag"):
                stats["links_siyi"] += 1

    await session.flush()
    stats["concepts"] = len(concepts)

    # Phase 3 — romanized-headword join: link Sanskrit/Pali entries to existing
    # concepts; fill display forms. Never creates new concepts.
    # Select only the 3 needed columns (NOT the definition Text) and stream in
    # batches — the sa/pi corpus is large (MW alone is ~32k rows); loading full
    # ORM entities with their definitions would balloon the session and risk OOM
    # on the prod container.
    result = await session.stream(
        select(DictionaryEntry.id, DictionaryEntry.headword, DictionaryEntry.lang)
        .where(DictionaryEntry.lang.in_(["sa", "pi"]))
        .execution_options(yield_per=2000)
    )
    async for eid, headword, lang in result:
        c = concepts.get(normalize_iast(headword))
        if c is None:
            continue
        lemma = (headword or "").split("\n")[0].strip()
        if lang == "pi":
            c.pali = c.pali or lemma
        # Prefer a dictionary lemma over Mahāvyutpatti's inflected citation form
        # (e.g. "nirvāṇa" over "nirvāṇam") when it's the same word.
        elif lang == "sa" and (
            not c.sanskrit or (lemma and c.sanskrit.startswith(lemma) and lemma != c.sanskrit)
        ):
            c.sanskrit = lemma
        if await link(c, eid, lang, "romanized_join"):
            stats["links_roman"] += 1

    # Phase 4 — Chinese back-link: concepts with a Chinese anchor pull in the
    # Chinese-headword dictionaries (佛光 / 丁福保 / …).
    chinese_index: dict[str, list[TermConcept]] = {}
    for c in concepts.values():
        if c.chinese:
            chinese_index.setdefault(c.chinese, []).append(c)
    if chinese_index:
        rows = await session.execute(
            select(DictionaryEntry.id, DictionaryEntry.headword)
            .where(
                DictionaryEntry.lang == "zh",
                DictionaryEntry.headword.in_(list(chinese_index.keys())),
            )
        )
        for eid, headword in rows:
            for c in chinese_index.get(headword, []):
                if await link(c, eid, "zh", "romanized_join", conf="medium"):
                    stats["links_zh"] += 1

    # Surface silent-no-op failure modes (wrong source codes / lang values in
    # prod data) instead of returning a clean-looking all-zero stats line.
    for phase, n in (
        ("links_mvp", stats["links_mvp"]),
        ("links_roman", stats["links_roman"]),
        ("links_zh", stats["links_zh"]),
    ):
        if n == 0:
            logger.warning("build_term_concepts: %s produced 0 links — check source codes / lang values", phase)

    await session.commit()
    return stats


async def main() -> int:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            stats = await build(session)
    finally:
        await engine.dispose()
    print(
        f"term concepts built: {stats['concepts']} concepts | "
        f"links mvp={stats['links_mvp']} siyi={stats['links_siyi']} "
        f"romanized={stats['links_roman']} zh={stats['links_zh']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
