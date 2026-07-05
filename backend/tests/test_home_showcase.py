"""Tests for the homepage dynamic showcase service.

Uses an in-memory SQLite DB seeded with a few rows so each card's real query
runs, plus asserts the two guarantees: independent per-card degradation
(a card with no data → None, page still returns) and time-bucket rotation.
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
from app.services.home_showcase import _pick, _seed, get_home_showcase

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
        s.add(KGRelation(subject_id=xuanzang.id, predicate="译", object_id=sutra.id))
        await s.commit()
        yield s
    await engine.dispose()


@pytest.mark.anyio
async def test_showcase_populates_each_card_from_real_data(seeded_db):
    out = await get_home_showcase(seeded_db, redis=None)
    assert out["sources"] == {"sources": 1, "texts": 1}
    # HOT_TERMS rotates; 般若 is in the list, and its definition is seeded, so
    # whichever term is picked, the dictionary card is a dict (never crashes).
    assert isinstance(out["dictionary"], dict)
    assert out["kg"] == {"subject": "玄奘", "predicate": "译", "object": "大般若經"}
    assert out["geo"]["count"] == 1
    assert "那烂陀寺" in out["geo"]["places"]
    assert isinstance(out["chat"], dict) and out["chat"]["question"]


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
    # No sources/texts, no KG, no geo → those cards None; chat still has the
    # DEFAULT_HOT_QUESTIONS fallback; dictionary term exists but no definition row.
    assert out["sources"] is None
    assert out["kg"] is None
    assert out["geo"] is None
    assert out["chat"]["question"]                      # default hot questions
    assert out["dictionary"]["definition"] is None      # term w/o seeded entry


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


def test_pick_rotates_by_seed():
    items = ["a", "b", "c"]
    assert _pick(items, 0) == "a"
    assert _pick(items, 1) == "b"
    assert _pick(items, 3) == "a"                        # wraps
    assert _pick([], 5) is None


def test_seed_is_stable_within_bucket(monkeypatch):
    # Anchor on a bucket boundary so "TTL-1 later" stays in the same bucket.
    base = home_showcase.SHOWCASE_TTL * 1000
    monkeypatch.setattr(home_showcase.time, "time", lambda: float(base))
    s1 = _seed()
    monkeypatch.setattr(home_showcase.time, "time", lambda: float(base + home_showcase.SHOWCASE_TTL - 1))
    assert _seed() == s1                                 # same bucket
    monkeypatch.setattr(home_showcase.time, "time", lambda: float(base + home_showcase.SHOWCASE_TTL))
    assert _seed() == s1 + 1                             # next bucket
