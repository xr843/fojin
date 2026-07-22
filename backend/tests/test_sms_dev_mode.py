"""SMS login must not leak one-time codes, and must not silently no-op.

`send_sms_code` fell back to a "development mode" whenever
`aliyun_sms_access_key_id` was empty — which is the state of production,
since the credential has no value in .env.example or the compose defaults.
In that mode it wrote a *valid login credential* for an arbitrary phone
number into the app log at WARNING level, and returned True so the endpoint
answered "验证码已发送" while sending nothing.

Anyone who could read `docker logs fojin-backend` — the stream CLAUDE.md
designates as the primary debugging entry point — could then POST
/auth/sms/login and, because that route auto-registers unknown numbers,
mint a JWT for any phone identity.

The dev-mode branch is now gated on FOJIN_ENV=development, and the code is
never logged in any environment.
"""

import logging
from unittest.mock import AsyncMock

import pytest

from app.services import oauth as oauth_module


@pytest.fixture
def redis_mock():
    r = AsyncMock()
    r.set = AsyncMock(return_value=True)
    r.get = AsyncMock(return_value=None)
    r.delete = AsyncMock(return_value=1)
    r.ttl = AsyncMock(return_value=-2)
    return r


@pytest.mark.asyncio
async def test_code_is_never_written_to_the_log(redis_mock, caplog, monkeypatch):
    monkeypatch.setattr(oauth_module.settings, "aliyun_sms_access_key_id", "")
    monkeypatch.setattr(oauth_module, "_SMS_DEV_MODE", True, raising=False)

    with caplog.at_level(logging.DEBUG):
        await oauth_module.send_sms_code("13800000000", redis_mock)

    # Whatever was stored in Redis is the live credential; it must not appear
    # anywhere in the captured log output.
    stored = [c.args[1] for c in redis_mock.set.await_args_list if "sms_code" in str(c.args[0])]
    assert stored, "no code was stored — test would pass vacuously"
    logged = caplog.text
    for code in stored:
        assert str(code) not in logged, f"one-time code {code} leaked into the log"


@pytest.mark.asyncio
async def test_production_without_credentials_reports_failure(redis_mock, monkeypatch):
    """No credentials in production must not read as a successful send."""
    monkeypatch.setattr(oauth_module.settings, "aliyun_sms_access_key_id", "")
    monkeypatch.setattr(oauth_module, "_SMS_DEV_MODE", False, raising=False)

    ok = await oauth_module.send_sms_code("13800000000", redis_mock)

    assert ok is False


@pytest.mark.asyncio
async def test_development_without_credentials_still_works(redis_mock, monkeypatch):
    """Local dev keeps working — it just can't learn the code from the log."""
    monkeypatch.setattr(oauth_module.settings, "aliyun_sms_access_key_id", "")
    monkeypatch.setattr(oauth_module, "_SMS_DEV_MODE", True, raising=False)

    ok = await oauth_module.send_sms_code("13800000000", redis_mock)

    assert ok is True
