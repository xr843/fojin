"""个人摘录：真库（SQLite）走一遍接口往返 + 迁移与 ORM 列名一致性。"""

import importlib.util
import pathlib
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.deps import get_current_user
from app.database import get_db
from app.main import app
from app.models.excerpt import UserExcerpt
from app.models.source import DataSource
from app.models.text import BuddhistText
from app.models.user import User


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for model in (User, DataSource, BuddhistText, UserExcerpt):
            await conn.run_sync(model.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        s.add(BuddhistText(id=15, cbeta_id="T0374", title_zh="大般涅槃經", has_content=True))
        await s.commit()
        yield s
    await engine.dispose()


def _client(db, user_id):
    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user_id)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.anyio
async def test_create_list_update_delete_roundtrip(db):
    async with _client(db, 1) as c:
        r = await c.post(
            "/api/excerpts",
            json={"text_id": 15, "juan_num": 8, "line_ref": "0413a07", "quote": " 有十四音名為字義 ", "note": "  "},
        )
        assert r.status_code == 200, r.text
        ex = r.json()
        assert ex["quote"] == "有十四音名為字義"  # 首尾空白去掉
        assert ex["note"] is None  # 空白笔记存成 None
        assert ex["title_zh"] == "大般涅槃經" and ex["cbeta_id"] == "T0374"

        r = await c.get("/api/excerpts", params={"text_id": 15, "juan_num": 8})
        assert [x["id"] for x in r.json()["items"]] == [ex["id"]]

        r = await c.patch(f"/api/excerpts/{ex['id']}", json={"note": "字本即涅槃"})
        assert r.json()["note"] == "字本即涅槃"

        assert (await c.delete(f"/api/excerpts/{ex['id']}")).status_code == 200
        assert (await c.get("/api/excerpts")).json()["total"] == 0


@pytest.mark.anyio
async def test_other_users_excerpts_are_invisible(db):
    async with _client(db, 1) as c:
        ex = (await c.post("/api/excerpts", json={"text_id": 15, "juan_num": 1, "quote": "如是我聞"})).json()
    async with _client(db, 2) as c:
        assert (await c.get("/api/excerpts")).json()["total"] == 0
        assert (await c.patch(f"/api/excerpts/{ex['id']}", json={"note": "x"})).status_code == 404
        assert (await c.delete(f"/api/excerpts/{ex['id']}")).status_code == 404
    async with _client(db, 1) as c:
        assert (await c.get("/api/excerpts")).json()["total"] == 1


@pytest.mark.anyio
async def test_validation(db):
    async with _client(db, 1) as c:
        assert (await c.post("/api/excerpts", json={"text_id": 999, "juan_num": 1, "quote": "x"})).status_code == 404
        assert (await c.post("/api/excerpts", json={"text_id": 15, "juan_num": 1, "quote": ""})).status_code == 422
        assert (await c.post("/api/excerpts", json={"text_id": 15, "juan_num": 1, "quote": "   "})).status_code == 422
        long = "字" * 501
        assert (await c.post("/api/excerpts", json={"text_id": 15, "juan_num": 1, "quote": long})).status_code == 422


def test_migration_columns_match_orm():
    """迁移建的列必须和 ORM 一模一样——门禁里没有真库往返，错配只会在生产炸。"""
    path = next(pathlib.Path(__file__).parents[1].glob("alembic/versions/0191_user_excerpts_*.py"))
    spec = importlib.util.spec_from_file_location("m0191", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    created = {}

    class FakeOp:
        def create_table(self, name, *cols):
            created[name] = {c.name: c for c in cols}

        def create_index(self, *a, **k):
            pass

    mod.op = FakeOp()
    mod.upgrade()
    mig = created["user_excerpts"]
    orm = UserExcerpt.__table__.columns
    assert set(mig) == {c.name for c in orm}
    for c in orm:
        assert mig[c.name].nullable == c.nullable, c.name
        assert type(mig[c.name].type).__name__ == type(c.type).__name__, c.name
