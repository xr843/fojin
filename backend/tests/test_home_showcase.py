"""Tests for the homepage dynamic showcase service.

Uses an in-memory SQLite DB seeded with a few rows so each card's real query
runs, and asserts: per-card POOLS (the frontend picks one at random per load),
independent per-card degradation (no data → None), and cache passthrough.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.dictionary import DictionaryEntry
from app.models.hot_question import HotQuestion
from app.models.knowledge_graph import KGEntity, KGRelation
from app.models.source import DataSource
from app.models.text import BuddhistText
from app.services import home_showcase
from app.services.home_showcase import _short_gloss, get_home_showcase

_MODELS = (BuddhistText, DataSource, DictionaryEntry, HotQuestion, KGEntity, KGRelation)


@pytest_asyncio.fixture
async def seeded_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for model in _MODELS:
            await conn.run_sync(model.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        source = DataSource(name_zh="CBETA", code="cbeta", is_active=True)
        s.add(source)
        await s.flush()
        s.add(BuddhistText(cbeta_id="T0001", title_zh="長阿含經", lang="lzh"))
        s.add(DictionaryEntry(
            headword="般若", definition="照见诸法实相的智慧。", lang="zh", source_id=source.id
        ))
        xuanzang = KGEntity(entity_type="person", name_zh="玄奘")
        sutra = KGEntity(entity_type="text", name_zh="大般若經")
        nalanda = KGEntity(entity_type="monastery", name_zh="那烂陀寺")
        s.add_all([xuanzang, sutra, nalanda])
        await s.flush()
        s.add(KGRelation(subject_id=xuanzang.id, predicate="translated", object_id=sutra.id))
        await s.commit()
        yield s
    await engine.dispose()


@pytest.mark.anyio
async def test_showcase_returns_pools_per_card(seeded_db):
    out = await get_home_showcase(seeded_db, redis=None)
    assert out["sources"]["sources"] == 1 and out["sources"]["texts"] == 1
    assert out["sources"]["names"] == ["CBETA"]          # active source name pool
    # KG returns a POOL of triples; the seeded translated→译 triple is in it.
    assert {"subject": "玄奘", "predicate": "译", "object": "大般若經"} in out["kg"]["triples"]
    # Dictionary returns a POOL of {term, definition}; 般若 (seeded) is present.
    terms = {e["term"] for e in out["dictionary"]["terms"]}
    assert "般若" in terms
    # count is the live geo total (1 seeded monastery); places are the CURATED
    # featured pool (not sampled from the DB, so foreign native names never leak
    # onto the homepage). The seeded 那烂陀寺 therefore does NOT appear.
    assert out["geo"]["count"] == 1
    assert out["geo"]["places"] == list(home_showcase._GEO_FEATURED)
    assert "少林寺" in out["geo"]["places"]
    assert "那烂陀寺" not in out["geo"]["places"]
    # Chat returns a non-empty pool of questions.
    assert isinstance(out["chat"]["questions"], list) and out["chat"]["questions"]
    # Legacy single-pick fields coexist (backward-compat for PWA-cached old FE).
    assert out["chat"]["question"] == out["chat"]["questions"][0]
    assert out["kg"]["subject"] == out["kg"]["triples"][0]["subject"]
    assert out["dictionary"]["term"] == out["dictionary"]["terms"][0]["term"]


@pytest.mark.anyio
async def test_empty_db_degrades_each_card_to_none_not_crash():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for model in _MODELS:
            await conn.run_sync(model.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        out = await get_home_showcase(s, redis=None)
    await engine.dispose()
    # No sources/texts, no KG, no geo, no dictionary rows → those cards None;
    # chat still has the DEFAULT_HOT_QUESTIONS fallback pool.
    assert out["sources"] is None
    assert out["kg"] is None
    assert out["geo"] is None
    assert out["dictionary"] is None                     # no HOT_TERMS entries seeded
    assert out["chat"]["questions"]                      # default hot questions


@pytest.mark.anyio
async def test_showcase_reads_from_redis_cache_when_present(seeded_db):
    class _Redis:
        def __init__(self, payload):
            self._payload = payload
        async def get(self, key):
            return self._payload
        async def set(self, *a, **k):
            pass

    import json
    sentinel = {"sources": {"sources": 999, "texts": 0}, "chat": None,
                "dictionary": None, "kg": None, "geo": None}
    out = await get_home_showcase(seeded_db, redis=_Redis(json.dumps(sentinel)))
    assert out == sentinel                               # served from cache, DB untouched


def test_geo_featured_pool_is_pure_chinese():
    """The whole point of curating the pool: no latin/hangul/kana names ever
    reach the homepage. Each featured name must be CJK-Han only (well-known
    temples — matching the card's 座佛教寺院 label)."""
    import re

    non_han = re.compile(r"[A-Za-z가-힣぀-ヿ]")  # latin / hangul / kana
    assert home_showcase._GEO_FEATURED, "featured pool must be non-empty"
    for name in home_showcase._GEO_FEATURED:
        assert not non_han.search(name), f"featured name not pure-Chinese: {name!r}"


@pytest.mark.anyio
async def test_dictionary_card_prefers_chinese_gloss_over_transliteration():
    """A term whose only gloss is a bare transliteration (如来 → "Tathagata")
    must be dropped, not shown; a term with both keeps the Chinese gloss."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(DictionaryEntry.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        s.add(DictionaryEntry(headword="如来", definition="Tathagata", lang="en"))
        s.add(DictionaryEntry(headword="般若", definition="prajñā", lang="sa"))
        s.add(DictionaryEntry(headword="般若", definition="照见诸法实相的智慧。", lang="zh"))
        await s.commit()
        card = await home_showcase._dictionary_card(s)
    await engine.dispose()

    terms = {t["term"]: t["definition"] for t in (card or {}).get("terms", [])}
    assert "如来" not in terms                       # English-only → dropped
    assert terms.get("般若") == "照见诸法实相的智慧"    # Chinese gloss chosen over prajñā


@pytest.mark.anyio
async def test_kg_card_pool_spans_multiple_predicates():
    """Regression for the "100% active_in→唐" bug: with translated + teacher_of
    + active_in data present, the pool must span more than one relation type."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(KGEntity.__table__.create)
        await conn.run_sync(KGRelation.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        kj = KGEntity(entity_type="person", name_zh="鸠摩罗什")
        dx = KGEntity(entity_type="person", name_zh="道宣")
        xz = KGEntity(entity_type="person", name_zh="玄奘")
        lotus = KGEntity(entity_type="text", name_zh="妙法莲华经")
        wg = KGEntity(entity_type="person", name_zh="文纲")
        tang = KGEntity(entity_type="dynasty", name_zh="唐")
        s.add_all([kj, dx, xz, lotus, wg, tang])
        await s.flush()
        s.add(KGRelation(subject_id=kj.id, predicate="translated", object_id=lotus.id))
        s.add(KGRelation(subject_id=dx.id, predicate="teacher_of", object_id=wg.id))
        s.add(KGRelation(subject_id=xz.id, predicate="active_in", object_id=tang.id))
        await s.commit()
        card = await home_showcase._kg_card(s)
    await engine.dispose()

    preds = {t["predicate"] for t in (card or {}).get("triples", [])}
    assert len(preds) >= 2, f"pool should span multiple predicates, got {preds}"
    assert "译" in preds and "授学" in preds


def test_short_gloss_trims_long_definitions():
    # Cuts at the first sentence break when it lands early.
    assert _short_gloss("法相以唯識為中道，三論以八不為中道，天台以實相為中道") == "法相以唯識為中道"
    # No early break → hard char cap with an ellipsis.
    long = "阿" * 40
    g = _short_gloss(long)
    assert g.endswith("…") and len(g) <= home_showcase._DEF_MAX_CHARS + 1
    # Short definition passes through unchanged; empty → None.
    assert _short_gloss("寂静") == "寂静"
    assert _short_gloss("") is None
    assert _short_gloss(None) is None
