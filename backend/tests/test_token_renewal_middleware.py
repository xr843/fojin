"""端到端：真的会在响应头里发回新 token，且只在该发的时候发。

策略本身在 test_token_renewal_policy.py 里单测。这里管的是接线：中间件能不能
读到依赖写进 request.state 的东西、头有没有真的发出去、以及最要紧的——**已被
吊销的会话不能被续期**。
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import Depends, FastAPI

from app.config import settings
from app.core.auth import create_access_token, decode_token_claims
from app.core.deps import get_current_user, get_optional_user
from app.main import RENEWED_TOKEN_HEADER, TokenRenewalMiddleware

pytestmark = pytest.mark.anyio


class FakeUser:
    def __init__(self, user_id=1, password_version=0):
        self.id = user_id
        self.password_version = password_version
        self.is_active = True


def _token(*, expires_in: timedelta, user_id=1, pwd_v=0, oit: datetime | None = None) -> str:
    """直接签一张任意寿命的 token —— create_access_token 只会签 8 小时的。"""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "pwd_v": pwd_v,
        "exp": now + expires_in,
        "oit": int((oit or now).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _app(*, resolves_to: FakeUser | None):
    """一个最小应用：真中间件 + 真依赖，只把"查库拿用户"这一步替换掉。"""
    app = FastAPI()
    app.add_middleware(TokenRenewalMiddleware)

    @app.get("/protected")
    async def protected(user=Depends(get_optional_user)):
        return {"user": getattr(user, "id", None)}

    async def _fake_db():
        yield None

    from app.core import deps as deps_mod
    from app.database import get_db

    async def fake_resolve(token, db):
        # 复刻真实 resolve_optional_user 的规则：签名无效或 pwd_v 不匹配 → None
        from app.core.auth import verify_token

        if not token:
            return None
        payload = verify_token(token)
        if payload is None or resolves_to is None:
            return None
        _uid, token_pwd_v = payload
        if resolves_to.password_version != token_pwd_v:
            return None
        return resolves_to

    app.dependency_overrides[get_db] = _fake_db
    return app, deps_mod, fake_resolve


async def _get(monkeypatch, *, token: str, resolves_to: FakeUser | None):
    import httpx

    app, deps_mod, fake_resolve = _app(resolves_to=resolves_to)
    monkeypatch.setattr(deps_mod, "resolve_optional_user", fake_resolve)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.get("/protected", headers={"Authorization": f"Bearer {token}"})


async def test_half_expired_token_comes_back_renewed(monkeypatch):
    resp = await _get(monkeypatch, token=_token(expires_in=timedelta(hours=1)), resolves_to=FakeUser())
    assert resp.status_code == 200
    fresh = resp.headers.get(RENEWED_TOKEN_HEADER)
    assert fresh, "过半程的请求应当带回一张新 token"
    claims = decode_token_claims(fresh)
    assert claims is not None
    # 新 token 寿命是满的，但会话起点保持不变
    assert claims["exp"] > (datetime.now(UTC) + timedelta(hours=7)).timestamp()
    assert claims["sub"] == "1"


async def test_fresh_token_is_left_alone(monkeypatch):
    resp = await _get(monkeypatch, token=_token(expires_in=timedelta(hours=7)), resolves_to=FakeUser())
    assert resp.status_code == 200
    assert RENEWED_TOKEN_HEADER not in resp.headers


async def test_anonymous_request_gets_no_token(monkeypatch):
    """没认证成功就没有续期凭据——中间件应当什么都不做。"""
    resp = await _get(monkeypatch, token=_token(expires_in=timedelta(hours=1)), resolves_to=None)
    assert resp.status_code == 200
    assert RENEWED_TOKEN_HEADER not in resp.headers


async def test_revoked_session_is_never_renewed(monkeypatch):
    """⭐ 安全承重点：用户改过密码（password_version 已加一）之后，
    旧 token 即便签名有效、即便正好过了半程，也绝不能被换发新证。

    如果中间件只凭签名判断——这是最容易写出来的版本——改密码这个吊销手段就被
    绕过了：旧会话会在每次请求里自动拿到一张全新的 token，永远吊销不掉。
    """
    stale = _token(expires_in=timedelta(hours=1), pwd_v=0)
    resp = await _get(monkeypatch, token=stale, resolves_to=FakeUser(password_version=1))
    assert resp.status_code == 200
    assert resp.json()["user"] is None, "pwd_v 不匹配时本就不该认证成功"
    assert RENEWED_TOKEN_HEADER not in resp.headers, "吊销的会话被续期了——密码吊销形同虚设"


async def test_session_past_absolute_cap_stops_renewing(monkeypatch):
    ancient = datetime.now(UTC) - timedelta(days=settings.jwt_absolute_max_days + 1)
    resp = await _get(
        monkeypatch,
        token=_token(expires_in=timedelta(hours=1), oit=ancient),
        resolves_to=FakeUser(),
    )
    assert resp.status_code == 200
    assert RENEWED_TOKEN_HEADER not in resp.headers


async def test_renewed_token_keeps_the_original_session_start(monkeypatch):
    """续期链必须一直带着原始 oit，否则上限每次都重新计时 = 没有上限。"""
    began = datetime.now(UTC) - timedelta(days=10)
    resp = await _get(
        monkeypatch,
        token=_token(expires_in=timedelta(hours=1), oit=began),
        resolves_to=FakeUser(),
    )
    fresh = resp.headers[RENEWED_TOKEN_HEADER]
    claims = decode_token_claims(fresh)
    assert claims["oit"] == int(began.timestamp()), "新 token 把会话起点重置了"


async def test_login_token_starts_a_new_session_clock():
    """真正登录签发的 token，oit 就是现在——不该继承任何旧起点。"""
    claims = decode_token_claims(create_access_token(1, 0))
    assert abs(claims["oit"] - datetime.now(UTC).timestamp()) < 5
