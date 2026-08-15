"""GET /api/chat/quota must say whether it recognised a logged-in user.

用户实拍复现（2026-08-15）：登录用户进入 /chat 就看到「今日免费额度快用完了，
剩余 10 次」，重新登录也不消失。查库发现该用户当日只用了 1 次（按登录上限 200，
真实剩余 199），当天全站最高用量 3 次，无人接近上限。

机制：JWT 只有 8 小时且无续期，``resolve_optional_user`` 对过期 token 静默返回
None，本接口于是落到匿名分支返回 ``limit: 10``。前端的 user 存在持久化 store 里，
token 过期了 user 对象还在，于是用「登录用户」的横幅渲染了「游客」的数字 ——
10 恰好是匿名满额（10 - 0），不是巧合。

两条分支此前对调用方完全无法区分，这就是歧义能变成用户可见谎言的原因。
``authenticated`` 是唯一让客户端分辨「你是游客」和「你的登录过期了」的信号。
"""

import pytest

pytestmark = pytest.mark.anyio


async def _quota(client, user):
    from app.core.deps import get_optional_user
    from app.main import app

    app.dependency_overrides[get_optional_user] = lambda: user
    try:
        resp = await client.get("/api/chat/quota")
        assert resp.status_code == 200, resp.text
        return resp.json()
    finally:
        app.dependency_overrides.pop(get_optional_user, None)


class _User:
    """Minimal stand-in — the endpoint only reads these four attributes."""

    def __init__(self, *, daily_chat_count=0, last_chat_date=None, encrypted_api_key=None):
        self.id = 1
        self.daily_chat_count = daily_chat_count
        self.last_chat_date = last_chat_date
        self.encrypted_api_key = encrypted_api_key


async def test_anonymous_visitor_is_reported_unauthenticated(client):
    body = await _quota(client, None)
    assert body["authenticated"] is False
    assert body["limit"] == 10


async def test_logged_in_user_is_reported_authenticated(client):
    from datetime import date

    body = await _quota(client, _User(daily_chat_count=1, last_chat_date=date.today()))
    assert body["authenticated"] is True
    assert body["limit"] == 200
    assert body["remaining"] == 199


async def test_expired_token_is_distinguishable_from_a_real_guest_quota(client):
    """承重点：这是用户实际撞到的那一格。

    token 过期后 get_optional_user 返回 None，本接口只能给出匿名配额 ——
    这部分改不了，也不该改。能改的是：响应里必须带上一个信号，让客户端不至于
    把这 10 次当成某个登录用户的余额报出去。

    只断言「匿名返回 limit 10」是不够的：修复前它同样成立，而 bug 照样发生。
    真正的断言是这个字段存在且为 False —— 客户端据此才能说「登录已过期」。
    """
    expired = await _quota(client, None)  # 过期 token 与无 token 在这一层无从区分
    assert expired["authenticated"] is False, (
        "少了这个字段，过期登录态和真游客返回完全一致，前端只能编一个余额出来"
    )


async def test_byok_user_reports_unlimited_and_authenticated(client):
    """自带 Key 的用户 remaining 是 -1（前端据此不弹额度提醒）。

    这条同时说明了为什么管理员自查不出这个 bug：remaining=-1 让额度横幅对他
    结构上不可达，除非他的 token 也过期 —— 而那时后端回的是匿名分支，
    has_byok 被硬编码成 False，他反而会看到一句自相矛盾的「配置自己的 API Key
    可不受此限制」。
    """
    body = await _quota(client, _User(encrypted_api_key="x"))
    assert body["authenticated"] is True
    assert body["remaining"] == -1
    assert body["has_byok"] is True
