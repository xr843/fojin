"""Characterisation tests for the dictionary headword count.

`count_distinct_headwords` decides how many `/sitemap-dict-N.xml` batches the
sitemap index advertises, so its value has to stay exact — an undercount
silently drops dictionary pages out of the index.

These pin the behaviour so the query underneath can be rewritten for speed.
On production (747,539 rows / 553,678 distinct headwords) the original
`count(DISTINCT headword)` took 13.7s, which was essentially the whole
20s `/sitemap.xml` response; `GROUP BY` returns the identical number in 1.5s
because PostgreSQL will not use an index for `count(DISTINCT ...)`.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.seo_dict import count_distinct_headwords
from app.models.dictionary import DictionaryEntry


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(DictionaryEntry.__table__.create)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _seed(db, pairs):
    """pairs: (headword, source_id)"""
    for i, (hw, src) in enumerate(pairs):
        db.add(DictionaryEntry(headword=hw, source_id=src, lang="zh", external_id=f"e{i}"))
    await db.commit()


@pytest.mark.asyncio
async def test_empty_table_is_zero(db):
    assert await count_distinct_headwords(db) == 0


@pytest.mark.asyncio
async def test_counts_each_headword_once(db):
    await _seed(db, [("空", 1), ("般若", 1), ("涅槃", 1)])
    assert await count_distinct_headwords(db) == 3


@pytest.mark.asyncio
async def test_same_headword_across_sources_counts_once(db):
    """The real table has ~747k rows but only ~554k distinct headwords —
    the same term defined by several dictionaries. Collapsing those is the
    entire point of the DISTINCT."""
    await _seed(db, [("空", 1), ("空", 2), ("空", 3), ("般若", 1), ("般若", 2)])
    assert await count_distinct_headwords(db) == 2


@pytest.mark.asyncio
async def test_headwords_differing_only_by_case_or_space_are_distinct(db):
    """No normalisation is applied — the count must match what
    get_distinct_headwords() actually paginates over."""
    await _seed(db, [("Buddha", 1), ("buddha", 1), ("Buddha ", 1)])
    assert await count_distinct_headwords(db) == 3
