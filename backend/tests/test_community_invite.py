"""fojin研读交流群邀请：名单与二维码只给名单里的已登录用户，任何异常都按「不邀请」处理。"""

import json
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import community
from app.core.deps import get_current_user
from app.services import community_invite as ci

LISTED, OUTSIDER = 650, 999
PNG = b"\x89PNG\r\n\x1a\n" + b"fake-qr-bytes"


class FakeRedis:
    def __init__(self, broken: bool = False):
        self.sets: dict[str, set[str]] = {}
        self.broken = broken

    async def sismember(self, key, member):
        if self.broken:
            raise ConnectionError("redis down")
        return member in self.sets.get(key, set())

    async def sadd(self, key, member):
        if self.broken:
            raise ConnectionError("redis down")
        self.sets.setdefault(key, set()).add(member)
        return 1


def write_invite(d, **cfg):
    d.mkdir(parents=True, exist_ok=True)
    (d / "invite.json").write_text(json.dumps({"enabled": True, "user_ids": [LISTED], **cfg}), encoding="utf-8")
    (d / "wechat-qr.png").write_bytes(PNG)


@pytest.fixture
def cdir(tmp_path, monkeypatch):
    d = tmp_path / "community"
    monkeypatch.setattr(ci, "COMMUNITY_DIR", d)
    return d


def make_app(user_id: int | None, redis=None) -> FastAPI:
    app = FastAPI()
    app.include_router(community.router, prefix="/api")
    app.state.redis = redis if redis is not None else FakeRedis()
    if user_id is not None:
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user_id)
    return app


@pytest_asyncio.fixture
async def call():
    async def _call(app, method, path):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            return await ac.request(method, path)

    return _call


@pytest.mark.asyncio
async def test_listed_user_sees_invite_and_gets_qr_without_caching(cdir, call):
    write_invite(cdir)
    app = make_app(LISTED)
    assert (await call(app, "GET", "/api/community/invite")).json() == {"invited": True}
    r = await call(app, "GET", "/api/community/invite/qr")
    assert r.status_code == 200
    assert r.content == PNG
    assert r.headers["content-type"] == "image/png"
    assert "no-store" in r.headers["cache-control"]
    assert "private" in r.headers["cache-control"]


@pytest.mark.asyncio
async def test_outsider_gets_nothing(cdir, call):
    write_invite(cdir)
    app = make_app(OUTSIDER)
    assert (await call(app, "GET", "/api/community/invite")).json() == {"invited": False}
    assert (await call(app, "GET", "/api/community/invite/qr")).status_code == 404


@pytest.mark.asyncio
async def test_outsider_dismiss_leaves_no_record(cdir, call):
    write_invite(cdir)
    redis = FakeRedis()
    app = make_app(OUTSIDER, redis)
    assert (await call(app, "POST", "/api/community/invite/dismiss")).json() == {"ok": True}
    assert redis.sets == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", [
    ("GET", "/api/community/invite"),
    ("GET", "/api/community/invite/qr"),
    ("POST", "/api/community/invite/dismiss"),
])
async def test_anonymous_requests_are_rejected(cdir, call, method, path):
    write_invite(cdir)
    r = await call(make_app(None), method, path)
    assert r.status_code in (401, 403)
    assert r.content != PNG


@pytest.mark.asyncio
async def test_dismiss_hides_card_for_good(cdir, call):
    write_invite(cdir)
    app = make_app(LISTED)
    assert (await call(app, "POST", "/api/community/invite/dismiss")).json() == {"ok": True}
    assert (await call(app, "GET", "/api/community/invite")).json() == {"invited": False}


@pytest.mark.asyncio
@pytest.mark.parametrize("setup", [
    "missing_dir",
    "disabled",
    "bad_json",
    "no_qr",
    "qr_too_big",
    "ids_not_a_list",
])
async def test_fails_closed(cdir, call, setup):
    if setup != "missing_dir":
        write_invite(cdir)
    if setup == "disabled":
        write_invite(cdir, enabled=False)
    elif setup == "bad_json":
        (cdir / "invite.json").write_text("{not json", encoding="utf-8")
    elif setup == "no_qr":
        (cdir / "wechat-qr.png").unlink()
    elif setup == "qr_too_big":
        (cdir / "wechat-qr.png").write_bytes(b"x" * (ci.QR_MAX_BYTES + 1))
    elif setup == "ids_not_a_list":
        write_invite(cdir, user_ids=str(LISTED))
    app = make_app(LISTED)
    assert (await call(app, "GET", "/api/community/invite")).json() == {"invited": False}
    assert (await call(app, "GET", "/api/community/invite/qr")).status_code == 404


@pytest.mark.asyncio
async def test_json_true_is_not_user_one(cdir, call):
    write_invite(cdir, user_ids=[True])
    assert (await call(make_app(1), "GET", "/api/community/invite")).json() == {"invited": False}
    assert (await call(make_app(1), "GET", "/api/community/invite/qr")).status_code == 404


@pytest.mark.asyncio
async def test_redis_down_means_no_card(cdir, call):
    write_invite(cdir)
    app = make_app(LISTED, FakeRedis(broken=True))
    assert (await call(app, "GET", "/api/community/invite")).json() == {"invited": False}
