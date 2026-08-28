"""端到端：真的会在响应头里发回新 token，且只在该发的时候发。

策略本身在 test_token_renewal_policy.py 里单测。这里管的是接线：中间件能不能
读到依赖写进 request.state 的东西、头有没有真的发出去、以及最要紧的——**已被
吊销的会话不能被续期**。
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import Depends, FastAPI, Request

from app.config import settings
from app.core.auth import create_access_token, decode_token_claims
from app.core.deps import clear_renewable, get_current_user, get_optional_user
from app.database import get_db
from app.main import RENEWED_TOKEN_HEADER, TokenRenewalMiddleware

pytestmark = pytest.mark.anyio

# 这些用例判的是"过没过半程"，不是"还剩几小时"。写成寿命的比例，改
# jwt_expire_minutes 时它们才继续测原来那件事——写死 7h/1h 的版本在寿命
# 从 8 小时改到 30 天时会静默变成"两张都过了半程"。
FULL_LIFE = timedelta(minutes=settings.jwt_expire_minutes)
PAST_HALFWAY = FULL_LIFE * 0.25  # 只剩四分之一 → 该续
STILL_FRESH = FULL_LIFE * 0.9  # 还剩九成 → 不该续


class FakeUser:
    def __init__(self, user_id=1, password_version=0):
        self.id = user_id
        self.password_version = password_version
        self.is_active = True


def _token(*, expires_in: timedelta, user_id=1, pwd_v=0, oit: datetime | None = None) -> str:
    """直接签一张任意寿命的 token —— create_access_token 只会签满寿命的。"""
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
    resp = await _get(monkeypatch, token=_token(expires_in=PAST_HALFWAY), resolves_to=FakeUser())
    assert resp.status_code == 200
    fresh = resp.headers.get(RENEWED_TOKEN_HEADER)
    assert fresh, "过半程的请求应当带回一张新 token"
    claims = decode_token_claims(fresh)
    assert claims is not None
    # 新 token 寿命是满的，但会话起点保持不变
    assert claims["exp"] > (datetime.now(UTC) + STILL_FRESH).timestamp()
    assert claims["sub"] == "1"


async def test_fresh_token_is_left_alone(monkeypatch):
    resp = await _get(monkeypatch, token=_token(expires_in=STILL_FRESH), resolves_to=FakeUser())
    assert resp.status_code == 200
    assert RENEWED_TOKEN_HEADER not in resp.headers


async def test_anonymous_request_gets_no_token(monkeypatch):
    """没认证成功就没有续期凭据——中间件应当什么都不做。"""
    resp = await _get(monkeypatch, token=_token(expires_in=PAST_HALFWAY), resolves_to=None)
    assert resp.status_code == 200
    assert RENEWED_TOKEN_HEADER not in resp.headers


async def test_revoked_session_is_never_renewed(monkeypatch):
    """⭐ 安全承重点：用户改过密码（password_version 已加一）之后，
    旧 token 即便签名有效、即便正好过了半程，也绝不能被换发新证。

    如果中间件只凭签名判断——这是最容易写出来的版本——改密码这个吊销手段就被
    绕过了：旧会话会在每次请求里自动拿到一张全新的 token，永远吊销不掉。
    """
    stale = _token(expires_in=PAST_HALFWAY, pwd_v=0)
    resp = await _get(monkeypatch, token=stale, resolves_to=FakeUser(password_version=1))
    assert resp.status_code == 200
    assert resp.json()["user"] is None, "pwd_v 不匹配时本就不该认证成功"
    assert RENEWED_TOKEN_HEADER not in resp.headers, "吊销的会话被续期了——密码吊销形同虚设"


async def test_session_past_absolute_cap_stops_renewing(monkeypatch):
    ancient = datetime.now(UTC) - timedelta(days=settings.jwt_absolute_max_days + 1)
    resp = await _get(
        monkeypatch,
        token=_token(expires_in=PAST_HALFWAY, oit=ancient),
        resolves_to=FakeUser(),
    )
    assert resp.status_code == 200
    assert RENEWED_TOKEN_HEADER not in resp.headers


async def test_renewed_token_keeps_the_original_session_start(monkeypatch):
    """续期链必须一直带着原始 oit，否则上限每次都重新计时 = 没有上限。"""
    began = datetime.now(UTC) - timedelta(days=settings.jwt_absolute_max_days // 2)
    resp = await _get(
        monkeypatch,
        token=_token(expires_in=PAST_HALFWAY, oit=began),
        resolves_to=FakeUser(),
    )
    fresh = resp.headers[RENEWED_TOKEN_HEADER]
    claims = decode_token_claims(fresh)
    assert claims["oit"] == int(began.timestamp()), "新 token 把会话起点重置了"


async def test_login_token_starts_a_new_session_clock():
    """真正登录签发的 token，oit 就是现在——不该继承任何旧起点。"""
    claims = decode_token_claims(create_access_token(1, 0))
    assert abs(claims["oit"] - datetime.now(UTC).timestamp()) < 5


# ── 吊销自身凭证的接口不得带回续期票 ─────────────────────────────────
#
# 鉴权依赖在**接口体跑之前**就把续期凭据（含**旧的** password_version）盖进
# request.state；接口随后 bump 了版本。中间件照单签发 = 一张签发即作废的票，
# 塞进 X-Renewed-Token 让客户端换上。前端因为随后会用响应体里的票覆盖而侥幸
# 无恙，但「靠别处纠正才对」不是能依赖的性质：别的客户端照收就是当场登出。


def _revoking_app(*, clear: bool):
    """最小的「吊销自身凭证」接口，可选择调不调 clear_renewable。"""
    user = FakeUser(password_version=3)
    app = FastAPI()
    app.add_middleware(TokenRenewalMiddleware)

    @app.post("/revoke")
    async def revoke(request: Request, _=Depends(get_current_user)):
        if clear:
            clear_renewable(request)
        user.password_version += 1  # change_user_password / revoke_all_sessions 做的事
        return {"version": user.password_version}

    class _Result:
        def scalar_one_or_none(self):
            return user

    class _Session:
        async def execute(self, *a, **k):
            return _Result()

    async def _fake_db():
        yield _Session()

    app.dependency_overrides[get_db] = _fake_db
    return app, user


async def _post_revoke(*, clear: bool):
    import httpx

    app, user = _revoking_app(clear=clear)
    token = _token(expires_in=PAST_HALFWAY, pwd_v=3)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        resp = await c.post("/revoke", headers={"Authorization": f"Bearer {token}"})
    return resp, user


async def test_revoking_endpoint_emits_no_renewed_token():
    resp, user = await _post_revoke(clear=True)
    assert resp.status_code == 200
    assert user.password_version == 4
    assert RENEWED_TOKEN_HEADER not in resp.headers


async def test_without_clearing_the_renewed_token_would_be_born_dead():
    """反向对照：不清凭据时，发出去的票签在**旧**版本上。

    不是在测产品行为，是在证明上一条真的挡住了什么 —— 少了它，
    「没有这个头」可能只是因为压根没走到续期分支。
    """
    resp, user = await _post_revoke(clear=False)
    stale = resp.headers.get(RENEWED_TOKEN_HEADER)
    assert stale, "这张票本该被签出来，否则上一条用例是恒真的"
    assert decode_token_claims(stale)["pwd_v"] == 3
    assert user.password_version == 4  # 签发的版本已经不存在了
