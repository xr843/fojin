"""SMS login ships off.

It is not a shipped feature — the frontend has no caller for either route —
but it was mounted in production anyway: two unauthenticated endpoints where
/auth/sms/login auto-registers any unknown phone number and issues a JWT for
it. An unmonitored auth surface with no users is all downside, so it is now
behind `settings.enable_sms_login`, default off, and the routes are not
registered at all when it is off (so they 404 and stay out of the OpenAPI
schema rather than existing as disabled stubs).

Re-enabling is an env var, not a code change — but production then requires
the full Aliyun credential set at boot, since an enabled-but-unconfigured
SMS login is the state that produced the original bug.
"""

import pytest

from app.config import settings


def test_ships_disabled_by_default():
    assert settings.enable_sms_login is False


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/auth/sms/send-code", {"phone": "13800000000"}),
        ("/api/auth/sms/login", {"phone": "13800000000", "code": "123456"}),
    ],
)
async def test_routes_are_not_mounted(client, path, payload):
    resp = await client.post(path, json=payload)
    assert resp.status_code == 404


def test_routes_absent_from_openapi():
    from app.main import app

    paths = app.openapi()["paths"]
    assert not [p for p in paths if "/sms/" in p], "SMS routes are still advertised in the schema"
