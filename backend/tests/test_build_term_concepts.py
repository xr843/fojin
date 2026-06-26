"""Integration test for the term-concept builder's DB logic (in-memory SQLite).

Parsing is covered by test_term_concepts.py; this exercises ``build()``
end-to-end — concept assembly, the four link phases, dedup, and the Phase-1
Pali boundary — without the prod corpus DB. Fixture rows mirror the real shape
of 翻譯名義大集 / 四譯合璧 entries for 涅槃 (nirvāṇa).
"""

import pytest_asyncio
from scripts.build_term_concepts import build
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.dictionary import DictionaryEntry
from app.models.source import DataSource
from app.models.term_concept import TermConcept, TermConceptEntry
from app.services.term_concept_service import resolve_concept

MVP_HEADWORD = "nirvāṇam\n            निर्वाणम्"
MVP_DEF = (
    "nirvāṇam\n  निर्वाणम्\n  涅槃\n  清淨涅槃\n"
    "  mya ngan las 'das pa\n  མྱ་ངན་ལས་འདས་པ་"
)
SIYI_DEF = "nirvāṇam\n【梵】nirvāṇam\n【漢】涅槃"


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for model in (DataSource, DictionaryEntry, TermConcept, TermConceptEntry):
            await conn.run_sync(model.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        await _seed(s)
        yield s
    await engine.dispose()


async def _seed(s):
    sources = {
        "dila-mvp": DataSource(code="dila-mvp", name_zh="翻譯名義大集"),
        "siyi-hebi": DataSource(code="siyi-hebi", name_zh="四譯合璧輯要"),
        "mw": DataSource(code="dila-mw", name_zh="Monier-Williams 梵英大辞典"),
        "dpd": DataSource(code="dpd", name_zh="数字巴利辞典 DPD"),
        "fg": DataSource(code="foguang", name_zh="佛光大辭典"),
    }
    s.add_all(list(sources.values()))
    await s.flush()
    s.add_all(
        [
            DictionaryEntry(headword=MVP_HEADWORD, definition=MVP_DEF, source_id=sources["dila-mvp"].id, lang="sa", external_id="mvp-1"),
            DictionaryEntry(headword="nirvāṇam", definition=SIYI_DEF, source_id=sources["siyi-hebi"].id, lang="sa,zh", external_id="siyi-1"),
            DictionaryEntry(headword="nirvāṇa", definition="extinction; liberation.", source_id=sources["mw"].id, lang="sa", external_id="mw-1"),
            DictionaryEntry(headword="nibbāna", definition="the unbinding.", source_id=sources["dpd"].id, lang="pi", external_id="dpd-1"),
            DictionaryEntry(headword="涅槃", definition="梵語 nirvāṇa 之音譯。", source_id=sources["fg"].id, lang="zh", external_id="fg-1"),
        ]
    )
    await s.commit()


async def _concepts(s):
    return (await s.execute(select(TermConcept))).scalars().all()


async def test_build_assembles_single_cross_lingual_concept(session):
    stats = await build(session)
    concepts = await _concepts(session)

    assert len(concepts) == 1
    c = concepts[0]
    assert c.key == "nirvana"
    assert c.chinese == "涅槃"  # first Chinese form from the Mahāvyutpatti entry
    # Phase 3 prefers the MW lemma "nirvāṇa" over the Mahāvyutpatti citation
    # form "nirvāṇam" for display (same word, lemma is a prefix).
    assert c.sanskrit == "nirvāṇa"
    assert c.tibetan == "མྱ་ངན་ལས་འདས་པ་"  # Tibetan script, not the Wylie line
    assert stats["concepts"] == 1


async def test_build_links_mvp_siyi_romanized_and_chinese(session):
    await build(session)
    rows = (await session.execute(select(TermConceptEntry))).scalars().all()
    methods = sorted(r.method for r in rows)
    # mvp + siyi_tag + romanized_join(MW) + romanized_join(佛光 zh back-link) = 4.
    assert methods == ["mvp", "romanized_join", "romanized_join", "siyi_tag"]
    # the佛光 Chinese back-link carries medium confidence.
    assert any(r.method == "romanized_join" and r.lang == "zh" and r.confidence == "medium" for r in rows)


async def test_build_respects_pali_boundary(session):
    """Phase 1: nibbāna (key 'nibbana') must NOT link to the nirvāṇa concept."""
    await build(session)
    entry_id = await session.scalar(
        select(DictionaryEntry.id).where(DictionaryEntry.headword == "nibbāna")
    )
    linked = await session.scalar(
        select(func.count())
        .select_from(TermConceptEntry)
        .where(TermConceptEntry.dict_entry_id == entry_id)
    )
    assert linked == 0


async def test_build_is_idempotent(session):
    first = await build(session)
    second = await build(session)
    assert first == second
    assert len(await _concepts(session)) == 1


# --- resolve_concept (the request-path) ------------------------------------


async def test_resolve_by_chinese_sanskrit_and_normalized_key(session):
    await build(session)
    # Chinese form, exact Sanskrit display form, and a romanized key variant
    # (no diacritics, accusative -m) must all resolve to the same concept.
    for term in ("涅槃", "nirvāṇa", "nirvanam"):
        res = await resolve_concept(session, term)
        assert res["concept"] is not None, term
        assert res["concept"]["chinese"] == "涅槃", term
        langs = {g["lang"] for g in res["entries_by_lang"]}
        assert {"zh", "sa"} <= langs, term  # grouped linked entries present


async def test_resolve_unknown_term_returns_empty(session):
    await build(session)
    res = await resolve_concept(session, "no-such-term-xyz")
    assert res == {"concept": None, "entries_by_lang": []}


async def test_resolve_blank_query_short_circuits(session):
    await build(session)
    assert await resolve_concept(session, "   ") == {"concept": None, "entries_by_lang": []}
