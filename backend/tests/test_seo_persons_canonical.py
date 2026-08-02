"""Tests for canonical-URL consolidation across duplicate KG person entities.

kg_entities has real-world duplicate persons sharing (name_zh, entity_type)
— e.g. 6 rows all named 法藏 — each rendering its own server-rendered SEO
page at /persons/{id}. Before this change every one of those pages
self-referenced its own canonical, splitting search-ranking signal across
N URLs instead of consolidating it on one (keyword cannibalization).

_find_canonical_person_id() picks one canonical id per duplicate cluster
(longest description wins, ties broken by smallest id); person_seo_html()
points that duplicate's <link rel="canonical"> (and og:url / JSON-LD url /
breadcrumb item, which intentionally reuse the same value) at it, while the
page BODY keeps rendering that entity's own content.
"""

import re
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.seo_persons import _DUPLICATE_CANDIDATES_LIMIT, _find_canonical_person_id
from app.models.knowledge_graph import KGEntity, KGRelation
from app.models.text import BuddhistText

_MODELS = (KGEntity, KGRelation, BuddhistText)


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for model in _MODELS:
            await conn.run_sync(model.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _mk(session, *, name_zh="法藏", entity_type="person", description=None):
    e = KGEntity(entity_type=entity_type, name_zh=name_zh, description=description)
    session.add(e)
    await session.flush()
    return e


# ---------------------------------------------------------------------------
# _find_canonical_person_id — the selection rule itself
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_no_duplicates_behavior_unchanged(db_session):
    """无同名（含不同 entity_type 的同名）实体时：解析结果就是自己的 id，行为与改动前一致。"""
    solo = await _mk(db_session, name_zh="独一无二法师", description="独有描述")
    await db_session.commit()

    assert await _find_canonical_person_id(db_session, solo) == solo.id


@pytest.mark.anyio
async def test_canonical_entity_self_references(db_session):
    """主实体（description 最长者）解析自己时，结果就是自己的 id。"""
    await _mk(db_session, description="短")
    longest = await _mk(db_session, description="这是一段明显更长的描述文字，用来确保它胜出成为主实体")
    await db_session.commit()

    assert await _find_canonical_person_id(db_session, longest) == longest.id


@pytest.mark.anyio
async def test_non_canonical_entity_points_to_longest_description(db_session):
    """非主实体（description 更短）解析时，结果指向 description 最长的那个主实体。"""
    short1 = await _mk(db_session, description="短")
    longest = await _mk(db_session, description="这是一段明显更长的描述文字，用来确保它胜出成为主实体")
    short2 = await _mk(db_session, description="也短一些")
    await db_session.commit()

    assert await _find_canonical_person_id(db_session, short1) == longest.id
    assert await _find_canonical_person_id(db_session, short2) == longest.id


@pytest.mark.anyio
async def test_tie_breaks_on_smallest_id(db_session):
    """描述长度相同（含都是 None / 空字符串）时，取 id 最小者为主实体。"""
    first = await _mk(db_session, description=None)
    second = await _mk(db_session, description=None)
    third = await _mk(db_session, description="")
    await db_session.commit()
    assert first.id < second.id < third.id

    for candidate in (first, second, third):
        assert await _find_canonical_person_id(db_session, candidate) == first.id


@pytest.mark.anyio
async def test_entity_type_scopes_the_duplicate_group(db_session):
    """同名但 entity_type 不同不算重复：各自把自己当主实体。"""
    person = await _mk(db_session, name_zh="观音", entity_type="person", description="人物条目")
    concept = await _mk(
        db_session, name_zh="观音", entity_type="concept", description="概念条目，故意写得更长一些"
    )
    await db_session.commit()

    assert await _find_canonical_person_id(db_session, person) == person.id
    assert await _find_canonical_person_id(db_session, concept) == concept.id


@pytest.mark.anyio
async def test_candidate_pool_capped_for_pathological_cluster(db_session):
    """同名实体数量超过上限时不炸查询：仍在合理时间内返回确定性结果。"""
    entities = [
        await _mk(db_session, name_zh="常见名", description=None)
        for _ in range(_DUPLICATE_CANDIDATES_LIMIT + 5)
    ]
    await db_session.commit()

    # All descriptions tie (None); winner among the (capped) id-ascending
    # candidates is the smallest id, i.e. the first one created.
    result = await _find_canonical_person_id(db_session, entities[0])
    assert result == entities[0].id


@pytest.mark.anyio
async def test_empty_name_zh_self_references(db_session):
    """name_zh 为空字符串时不做重复查询，直接自指（防御空字符串的病态大集合）。"""
    blank = KGEntity(entity_type="person", name_zh="", description="x")
    db_session.add(blank)
    await db_session.flush()
    await db_session.commit()

    assert await _find_canonical_person_id(db_session, blank) == blank.id


# ---------------------------------------------------------------------------
# Full route — the resolved id actually reaches the rendered HTML
# ---------------------------------------------------------------------------


def _extract_canonical_href(html: str) -> str | None:
    m = re.search(r'<link rel="canonical" href="([^"]+)" />', html)
    return m.group(1) if m else None


@pytest_asyncio.fixture
async def seo_client(db_session):
    """Real HTTP client; ES/Redis stubbed, DB is the real in-memory SQLite session."""
    with (
        patch("app.core.elasticsearch.init_es", new_callable=AsyncMock),
        patch("app.core.elasticsearch.close_es", new_callable=AsyncMock),
        patch("app.main.aioredis") as mock_redis_mod,
    ):
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_redis_mod.from_url.return_value = mock_redis

        from app.database import get_db
        from app.main import app

        async def fake_get_db():
            yield db_session

        app.dependency_overrides[get_db] = fake_get_db
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac
        finally:
            app.dependency_overrides.pop(get_db, None)


@pytest.mark.anyio
async def test_route_points_non_canonical_duplicate_at_winner(db_session, seo_client):
    """端到端：短描述重复实体的响应里，canonical / og:url 都指向长描述的主实体，
    但页面正文仍然渲染自己的内容（用户可见行为不变）。"""
    short = await _mk(db_session, description="短版生平")
    longest = await _mk(
        db_session, description="这是明显更长的一段人物生平描述文字，用来确保它胜出成为主实体页面"
    )
    await db_session.commit()

    resp = await seo_client.get(f"/persons/{short.id}")

    assert resp.status_code == 200
    body = resp.text
    expected = f"http://test/persons/{longest.id}"
    assert _extract_canonical_href(body) == expected
    assert f'<meta property="og:url" content="{expected}" />' in body
    # Body still describes the entity actually requested, not the canonical one.
    assert "短版生平" in body


@pytest.mark.anyio
async def test_route_canonical_entity_self_references(db_session, seo_client):
    """端到端：主实体自己的页面，canonical 指向自己（不变行为的一个特例）。"""
    await _mk(db_session, description="短版生平")
    longest = await _mk(
        db_session, description="这是明显更长的一段人物生平描述文字，用来确保它胜出成为主实体页面"
    )
    await db_session.commit()

    resp = await seo_client.get(f"/persons/{longest.id}")

    assert resp.status_code == 200
    expected = f"http://test/persons/{longest.id}"
    assert _extract_canonical_href(resp.text) == expected


@pytest.mark.anyio
async def test_route_no_duplicates_self_references_like_before(db_session, seo_client):
    """端到端：没有同名实体时，canonical 依旧自指——完全复现改动前的行为。"""
    solo = await _mk(db_session, name_zh="独一无二法师", description="独有描述")
    await db_session.commit()

    resp = await seo_client.get(f"/persons/{solo.id}")

    assert resp.status_code == 200
    expected = f"http://test/persons/{solo.id}"
    assert _extract_canonical_href(resp.text) == expected
