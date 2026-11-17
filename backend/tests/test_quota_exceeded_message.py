"""额度用完的文案：游客的出路是登录（每天 200 次），不是配 API Key。

生产 30 天（2026-11-17 Umami）：9 个游客会话撞了 50 次额度、全都接着再问，只有 3 个去了登录页
——原文案只说「配置自己的 API Key 可无限使用」。
"""

import pytest

from app.core.exceptions import QuotaExceededError
from app.services import chat_quota


class _Redis:
    def __init__(self, n: int):
        self.n = n

    async def incr(self, key):
        self.n += 1
        return self.n

    async def expire(self, key, ttl):
        return True


@pytest.mark.asyncio
async def test_guest_over_quota_is_told_to_sign_in_with_the_real_daily_limit():
    with pytest.raises(QuotaExceededError) as ei:
        await chat_quota._check_anonymous_quota(_Redis(chat_quota.FREE_DAILY_LIMIT_ANONYMOUS), "1.2.3.4")
    msg = str(ei.value)
    assert "登录" in msg and f"{chat_quota.FREE_DAILY_LIMIT_USER} 次" in msg
    assert "API Key" not in msg


@pytest.mark.asyncio
async def test_guest_under_quota_passes():
    await chat_quota._check_anonymous_quota(_Redis(0), "1.2.3.4")


def test_logged_in_over_quota_still_points_to_own_api_key():
    # 登录用户已经是最高免费额度，出路仍是自带 Key
    msg = str(QuotaExceededError(limit=200))
    assert "API Key" in msg and "登录" not in msg
