"""Tests for SMS OTP brute-force protection.

Regression guard for the account-takeover vector: ``verify_sms_code`` had
no per-phone attempt limit, so an attacker with a proxy pool could brute
force the 6-digit code within its 5-minute TTL (the global rate limit is
per-IP, not per-phone). The fix caps verification attempts per issued code
and burns the code once the budget is exhausted.
"""

import pytest

from app.services.oauth import (
    _SMS_MAX_ATTEMPTS,
    send_sms_code,
    verify_sms_code,
)


class FakeRedis:
    """Minimal in-memory async Redis for the ops these functions use.

    Behaves like a real Redis with ``decode_responses=True`` (values come
    back as ``str``). TTLs are not simulated; tests clear keys manually to
    emulate expiry.
    """

    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return None
        self.store[key] = str(value)
        return True

    async def delete(self, *keys):
        removed = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                removed += 1
        return removed

    async def incr(self, key):
        value = int(self.store.get(key, 0)) + 1
        self.store[key] = str(value)
        return value

    async def expire(self, key, ttl):
        return key in self.store

    async def exists(self, key):
        return 1 if key in self.store else 0


PHONE = "13800001234"


@pytest.mark.anyio
async def test_correct_code_succeeds_and_is_consumed():
    r = FakeRedis()
    assert await send_sms_code(PHONE, r) is True
    code = r.store[f"sms_code:{PHONE}"]

    assert await verify_sms_code(PHONE, code, r) is True
    # Single-use: the code and attempt counter are cleared on success.
    assert f"sms_code:{PHONE}" not in r.store
    assert f"sms_attempt:{PHONE}" not in r.store


@pytest.mark.anyio
async def test_wrong_code_fails_but_keeps_code_within_budget():
    r = FakeRedis()
    await send_sms_code(PHONE, r)
    code = r.store[f"sms_code:{PHONE}"]
    wrong = "000000" if code != "000000" else "111111"

    # One wrong guess must not invalidate a still-valid code.
    assert await verify_sms_code(PHONE, wrong, r) is False
    assert await verify_sms_code(PHONE, code, r) is True


@pytest.mark.anyio
async def test_bruteforce_is_capped_and_burns_the_code():
    r = FakeRedis()
    await send_sms_code(PHONE, r)
    code = r.store[f"sms_code:{PHONE}"]
    wrong = "000000" if code != "000000" else "111111"

    # Exhaust the attempt budget with wrong guesses.
    for _ in range(_SMS_MAX_ATTEMPTS):
        assert await verify_sms_code(PHONE, wrong, r) is False

    # Budget exhausted → the code is burned; even the CORRECT code is rejected.
    assert await verify_sms_code(PHONE, code, r) is False
    assert f"sms_code:{PHONE}" not in r.store


@pytest.mark.anyio
async def test_second_send_within_window_is_rate_limited_and_preserves_code():
    r = FakeRedis()
    assert await send_sms_code(PHONE, r) is True
    original = r.store[f"sms_code:{PHONE}"]

    # A throttled resend must not overwrite the live code.
    assert await send_sms_code(PHONE, r) is False
    assert r.store[f"sms_code:{PHONE}"] == original


@pytest.mark.anyio
async def test_new_send_resets_attempt_budget():
    r = FakeRedis()
    await send_sms_code(PHONE, r)
    code = r.store[f"sms_code:{PHONE}"]
    wrong = "000000" if code != "000000" else "111111"

    for _ in range(_SMS_MAX_ATTEMPTS):
        await verify_sms_code(PHONE, wrong, r)

    # Simulate the 1/min rate window elapsing, then resend.
    await r.delete(f"sms_rate:{PHONE}")
    assert await send_sms_code(PHONE, r) is True
    fresh = r.store[f"sms_code:{PHONE}"]

    # Fresh code → fresh attempt budget: the new code verifies.
    assert await verify_sms_code(PHONE, fresh, r) is True


def test_sms_endpoints_are_strict_rate_limited():
    """Both SMS endpoints must be in STRICT_PATHS (per-IP defense in depth)."""
    from app.core.rate_limit import STRICT_PATHS

    assert "/api/auth/sms/send-code" in STRICT_PATHS
    assert "/api/auth/sms/login" in STRICT_PATHS
