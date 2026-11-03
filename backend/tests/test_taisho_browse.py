"""读经页「按部类浏览」：大正藏编号区间列经目。"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import get_db
from app.main import app
from app.models.source import DataSource
from app.models.text import BuddhistText
from app.services.text import browse_taisho


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for model in (DataSource, BuddhistText):
            await conn.run_sync(model.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        s.add_all([
            BuddhistText(cbeta_id="T0001", title_zh="長阿含經", has_content=True, fascicle_count=22),
            BuddhistText(cbeta_id="T0151", title_zh="阿含正行經", has_content=True),
            BuddhistText(cbeta_id="T0152", title_zh="六度集經", has_content=True),  # 本緣部，区间外
            BuddhistText(cbeta_id="T0100", title_zh="無正文", has_content=False),
            BuddhistText(cbeta_id="T0099b", title_zh="變體", has_content=True),
            BuddhistText(cbeta_id="X0001", title_zh="續藏", has_content=True),
        ])
        await s.commit()
        yield s
    await engine.dispose()


@pytest.mark.anyio
async def test_range_is_inclusive_sorted_and_content_only(db):
    rows = await browse_taisho(db, 1, 151)
    assert [r["cbeta_id"] for r in rows] == ["T0001", "T0099b", "T0151"]
    assert rows[0]["fascicle_count"] == 22


@pytest.mark.anyio
async def test_endpoint_returns_list_and_validates_range(db):
    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            ok = await c.get("/api/texts/browse/taisho", params={"from_no": 1, "to_no": 151})
            assert ok.status_code == 200
            assert [r["cbeta_id"] for r in ok.json()] == ["T0001", "T0099b", "T0151"]
            assert "max-age" in ok.headers["cache-control"]
            assert (await c.get("/api/texts/browse/taisho", params={"from_no": 10, "to_no": 5})).status_code == 422
            assert (await c.get("/api/texts/browse/taisho", params={"from_no": 1, "to_no": 2000})).status_code == 422
    finally:
        app.dependency_overrides.pop(get_db, None)
