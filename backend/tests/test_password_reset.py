"""忘记密码：一次性重置链接、找回申请、登录失败原因计数。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import InvalidCredentialsError
from app.models.feedback import Feedback
from app.models.user import PasswordChangeAudit
from app.services import password_reset as pr
from app.services.auth import login_user


@pytest.fixture(autouse=True)
def _restore_app_redis():
    """接口用例会往 app.state.redis 装假 Redis；用完还原，别漏给后面的测试。"""
    from app.main import app

    sentinel = object()
    original = getattr(app.state, "redis", sentinel)
    yield
    if original is sentinel:
        if hasattr(app.state, "redis"):
            delattr(app.state, "redis")
    else:
        app.state.redis = original


class FakeRedis:
    """够这几个函数用的最小内存 Redis（GETDEL / SET NX / HINCRBY / ZADD）。"""

    def __init__(self):
        self.kv: dict[str, str] = {}
        self.hashes: dict[str, dict[str, int]] = {}
        self.zsets: dict[str, dict[str, float]] = {}

    async def get(self, k):
        return self.kv.get(k)

    async def set(self, k, v, ex=None, nx=False):
        if nx and k in self.kv:
            return None
        self.kv[k] = v
        return True

    async def getdel(self, k):
        return self.kv.pop(k, None)

    async def delete(self, *ks):
        for k in ks:
            self.kv.pop(k, None)
        return 1

    async def hincrby(self, k, f, n):
        h = self.hashes.setdefault(k, {})
        h[f] = h.get(f, 0) + n
        return h[f]

    async def zadd(self, k, mapping):
        self.zsets.setdefault(k, {}).update(mapping)

    async def expire(self, k, ttl):
        return True


def _user(uid=7, pv=2, active=True, username="huiming", email="hm@example.com"):
    u = MagicMock()
    u.id = uid
    u.password_version = pv
    u.is_active = active
    u.username = username
    u.email = email
    u.hashed_password = "hash:old"
    return u


def _db_returning(user):
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=user)
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


def _added(db, cls):
    return [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], cls)]


# ── 一次性链接 ─────────────────────────────────────────────


@pytest.mark.anyio
async def test_link_sets_password_once_and_revokes_old_sessions():
    redis, user = FakeRedis(), _user(pv=2)
    token = await pr.issue_reset_token(redis, user)
    assert token not in str(redis.kv)  # 只存摘要，不存明文令牌

    db = _db_returning(user)
    with patch("app.services.password_reset.hash_password", return_value="hash:new"):
        await pr.reset_password_with_token(db, redis, token, "newpass123", client_ip="203.0.113.9")

    assert user.hashed_password == "hash:new"
    assert user.password_version == 3  # 所有旧登录失效
    audit = _added(db, PasswordChangeAudit)
    assert len(audit) == 1 and audit[0].via == "reset_link" and audit[0].user_id == 7

    # 第二次用同一链接：失效
    with pytest.raises(pr.ResetLinkInvalidError):
        await pr.reset_password_with_token(_db_returning(user), redis, token, "another123")


@pytest.mark.anyio
async def test_new_link_voids_previous_one():
    redis, user = FakeRedis(), _user()
    first = await pr.issue_reset_token(redis, user)
    second = await pr.issue_reset_token(redis, user)
    with pytest.raises(pr.ResetLinkInvalidError):
        await pr.reset_password_with_token(_db_returning(user), redis, first, "newpass123")
    with patch("app.services.password_reset.hash_password", return_value="hash:new"):
        await pr.reset_password_with_token(_db_returning(user), redis, second, "newpass123")


@pytest.mark.anyio
async def test_link_dies_if_user_changed_password_meanwhile():
    """管理员手里的旧链接不能覆盖用户自己后来改的密码。"""
    redis, user = FakeRedis(), _user(pv=2)
    token = await pr.issue_reset_token(redis, user)
    user.password_version = 3  # 用户自己改过密码 / 退出了所有设备
    with pytest.raises(pr.ResetLinkInvalidError):
        await pr.reset_password_with_token(_db_returning(user), redis, token, "newpass123")
    assert user.hashed_password == "hash:old"


@pytest.mark.anyio
async def test_link_refused_for_disabled_account():
    redis, user = FakeRedis(), _user()
    token = await pr.issue_reset_token(redis, user)
    user.is_active = False
    with pytest.raises(pr.ResetLinkInvalidError):
        await pr.reset_password_with_token(_db_returning(user), redis, token, "newpass123")


@pytest.mark.anyio
async def test_bogus_token_rejected():
    with pytest.raises(pr.ResetLinkInvalidError):
        await pr.reset_password_with_token(_db_returning(_user()), FakeRedis(), "x" * 43, "newpass123")


# ── 找回申请 ──────────────────────────────────────────────


@pytest.mark.anyio
async def test_request_for_existing_account_lands_in_admin_inbox_once():
    redis, user = FakeRedis(), _user(username="huiming")
    db = _db_returning(user)
    await pr.submit_reset_request(db, redis, " huiming ", "微信 hm123")
    rows = _added(db, Feedback)
    assert len(rows) == 1
    assert rows[0].user_id == 7
    assert rows[0].content.startswith(pr.REQUEST_CONTENT_PREFIX)
    assert "用户名" in rows[0].content
    assert rows[0].contact == "微信 hm123"

    # 24 小时内再申请：不再进收件箱
    db2 = _db_returning(user)
    await pr.submit_reset_request(db2, redis, "huiming", "微信 hm123")
    assert _added(db2, Feedback) == []


@pytest.mark.anyio
async def test_request_for_unknown_account_writes_nothing_but_is_counted():
    redis = FakeRedis()
    db = _db_returning(None)
    await pr.submit_reset_request(db, redis, "nobody", "a@b.c")
    assert _added(db, Feedback) == []
    day_hash = next(iter(redis.hashes.values()))
    assert day_hash == {"reset_request_unmatched": 1}


@pytest.mark.anyio
async def test_reset_request_endpoint_answers_the_same_either_way(client):
    """账号存在与否，接口回的一样——不能拿来探测账号。"""
    from app.main import app

    app.state.redis = FakeRedis()
    with patch("app.api.auth.submit_reset_request", new=AsyncMock()) as sub:
        r1 = await client.post("/api/auth/reset-request", json={"account": "huiming", "contact": "微信 hm123"})
        r2 = await client.post("/api/auth/reset-request", json={"account": "nobody", "contact": "微信 hm123"})
    assert r1.status_code == r2.status_code == 200
    assert r1.json() == r2.json() == {"ok": True}
    assert sub.await_count == 2


@pytest.mark.anyio
async def test_reset_password_endpoint_rejects_weak_password_before_touching_token(client):
    from app.main import app

    app.state.redis = FakeRedis()
    with patch("app.api.auth.reset_password_with_token", new=AsyncMock()) as consume:
        r = await client.post("/api/auth/reset-password", json={"token": "t" * 43, "new_password": "short"})
    assert r.status_code == 422
    consume.assert_not_awaited()  # 弱密码不能烧掉令牌


# ── 登录失败原因 ──────────────────────────────────────────


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("found", "username", "reason", "badpw_uid"),
    [
        (None, "huiming", "no_user", None),
        (None, "hm@example.com", "no_user_email_shape", None),
        ("user", "huiming", "bad_password", "7"),
    ],
)
async def test_login_failure_reason_is_counted(found, username, reason, badpw_uid):
    redis = FakeRedis()
    db = _db_returning(_user() if found else None)
    with patch("app.services.auth.verify_password", return_value=False), pytest.raises(InvalidCredentialsError):
        await login_user(db, username, "wrong", redis)
    day_hash = next(iter(redis.hashes.values()))
    assert day_hash == {reason: 1}
    assert list(redis.zsets.get(pr.LOGIN_BADPW_KEY, {}).keys()) == ([badpw_uid] if badpw_uid else [])


@pytest.mark.anyio
async def test_login_counter_never_breaks_login_when_redis_is_down():
    broken = MagicMock()
    broken.hincrby = AsyncMock(side_effect=ConnectionError("down"))
    db = _db_returning(None)
    with patch("app.services.auth.verify_password", return_value=False), pytest.raises(InvalidCredentialsError):
        await login_user(db, "huiming", "wrong", broken)
