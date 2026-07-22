"""The OAuth `state` must be bound to the browser that started the flow.

Previously `state` was only a Redis key whose stored value was the provider
name, so *any* state an attacker minted for themselves validated for anyone.
That is login CSRF: the attacker starts a flow, captures their own `code`
without visiting the callback, then gets the victim to load

    /api/auth/github/callback?code=<attacker_code>&state=<attacker_state>

The victim's browser is redirected into the SPA, redeems the exchange code,
and is silently signed in as the attacker — so their subsequent chats,
bookmarks and uploads land in an account the attacker reads.

The state is now also written to an HttpOnly cookie at /login and must match
at /callback, which an attacker cannot set in the victim's browser.

SameSite must be Lax, not Strict: the callback is a cross-site top-level
navigation from github.com/accounts.google.com, and Strict would withhold
the cookie there and break every login.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest

from app.api.auth import _state_cookie_name


@pytest.fixture(autouse=True)
def _isolate_app_state_redis():
    from app.main import app

    sentinel = object()
    original = getattr(app.state, "redis", sentinel)
    try:
        yield
    finally:
        if original is sentinel:
            if hasattr(app.state, "redis"):
                delattr(app.state, "redis")
        else:
            app.state.redis = original


def _install_redis(*, get_return=None):
    from app.main import app

    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=get_return)
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.delete = AsyncMock(return_value=1)
    redis_mock.getdel = AsyncMock(return_value=None)
    redis_mock.ping = AsyncMock(return_value=True)
    redis_mock.incr = AsyncMock(return_value=1)
    redis_mock.expire = AsyncMock(return_value=True)
    app.state.redis = redis_mock
    return redis_mock


def _state_from_authorize_url(url: str) -> str:
    return parse_qs(urlparse(url).query)["state"][0]


@pytest.mark.anyio
@pytest.mark.parametrize("provider", ["github", "google"])
async def test_login_sets_httponly_state_cookie_matching_the_url(client, provider):
    _install_redis()

    resp = await client.get(f"/api/auth/{provider}/login")

    assert resp.status_code == 200
    cookie = resp.cookies.get(_state_cookie_name(provider))
    assert cookie is not None, "no state cookie was set"
    assert cookie == _state_from_authorize_url(resp.json()["url"])

    raw = resp.headers["set-cookie"].lower()
    assert "httponly" in raw
    # Strict would not be sent on the cross-site callback navigation.
    assert "samesite=lax" in raw


@pytest.mark.anyio
@pytest.mark.parametrize("provider", ["github", "google"])
async def test_callback_without_the_cookie_is_rejected(client, provider):
    """The login-CSRF case: attacker supplies a state Redis knows about."""
    _install_redis(get_return=provider)

    resp = await client.get(
        f"/api/auth/{provider}/callback",
        params={"code": "attacker-code", "state": "attacker-state"},
        follow_redirects=False,
    )

    assert resp.status_code in (302, 307)
    assert "error=invalid_state" in resp.headers["location"]


@pytest.mark.anyio
@pytest.mark.parametrize("provider", ["github", "google"])
async def test_callback_with_a_mismatched_cookie_is_rejected(client, provider):
    _install_redis(get_return=provider)

    resp = await client.get(
        f"/api/auth/{provider}/callback",
        params={"code": "c", "state": "state-from-attacker"},
        cookies={_state_cookie_name(provider): "state-of-this-browser"},
        follow_redirects=False,
    )

    assert resp.status_code in (302, 307)
    assert "error=invalid_state" in resp.headers["location"]


@pytest.mark.anyio
@pytest.mark.parametrize("provider", ["github", "google"])
async def test_callback_with_matching_cookie_passes_the_state_check(client, provider):
    """Matching cookie → the flow proceeds past state validation.

    The provider exchange itself is unmocked and fails, which is fine: the
    assertion is that we get the provider-failure branch, not invalid_state.
    """
    _install_redis(get_return=provider)

    resp = await client.get(
        f"/api/auth/{provider}/callback",
        params={"code": "c", "state": "agreed-state"},
        cookies={_state_cookie_name(provider): "agreed-state"},
        follow_redirects=False,
    )

    assert resp.status_code in (302, 307)
    assert "error=invalid_state" not in resp.headers["location"]


class TestStateComparisonRobustness:
    """Edge cases that must not 500 or break concurrent logins."""

    @pytest.mark.parametrize("provider", ["github", "google"])
    def test_non_ascii_cookie_is_rejected_not_raised(self, provider):
        """`secrets.compare_digest` raises TypeError on non-ASCII *str*.

        Starlette decodes request headers as latin-1, so raw bytes 128-255 in
        a Cookie header surface as a non-ASCII str even though httpx refuses
        to send one — hence this drives the predicate directly rather than
        going through the test client. It must return False, not raise, or the
        auth callback 500s instead of redirecting to invalid_state.
        """
        from app.api.auth import _state_is_valid

        request = SimpleNamespace(cookies={_state_cookie_name(provider): "caf\xe9-not-ascii"})

        assert _state_is_valid(request, "ascii-state", provider, provider) is False

    @pytest.mark.anyio
    async def test_two_providers_do_not_clobber_each_other(self, client):
        """Starting a GitHub flow must not invalidate an in-flight Google one."""
        _install_redis()
        gh = await client.get("/api/auth/github/login")
        goog = await client.get("/api/auth/google/login")

        gh_cookie = gh.cookies.get(_state_cookie_name("github"))
        goog_cookie = goog.cookies.get(_state_cookie_name("google"))

        assert gh_cookie and goog_cookie
        assert gh_cookie != goog_cookie, "both providers share one cookie slot"


class TestCookieHardening:
    """Attributes that decide whether the binding actually holds."""

    @pytest.mark.anyio
    @pytest.mark.parametrize("provider", ["github", "google"])
    async def test_cookie_is_scoped_and_secure_in_production(self, client, provider, monkeypatch):
        """Path is the attribute most likely to silently break every login.

        Under an https base the name must also carry the `__Host-` prefix,
        which browsers only accept with Secure + Path=/ + no Domain — that is
        what stops a sibling host (e.g. analytics.fojin.app) from tossing in a
        same-named cookie. Starlette's cookie parser takes the LAST duplicate,
        and RFC 6265 orders by decreasing path length, so a tossed `Path=/`
        cookie would otherwise beat the real one.
        """
        from app.api import auth as auth_module

        monkeypatch.setattr(auth_module.settings, "oauth_redirect_base", "https://fojin.app")
        _install_redis()

        resp = await client.get(f"/api/auth/{provider}/login")
        raw = resp.headers["set-cookie"].lower()

        assert "__host-" in raw
        assert "path=/;" in raw or raw.rstrip().endswith("path=/")
        assert "secure" in raw
        assert "domain=" not in raw

    @pytest.mark.anyio
    @pytest.mark.parametrize("provider", ["github", "google"])
    async def test_consumed_state_is_rejected_even_with_a_matching_cookie(self, client, provider):
        """Replay guard: Redis is the one-shot half of the pair.

        After a successful callback the key is deleted, but the browser may
        still hold the cookie (back button, retried redirect). The stale
        cookie alone must not authenticate anything.
        """
        _install_redis(get_return=None)  # key already consumed

        resp = await client.get(
            f"/api/auth/{provider}/callback",
            params={"code": "c", "state": "replayed-state"},
            cookies={_state_cookie_name(provider): "replayed-state"},
            follow_redirects=False,
        )

        assert "error=invalid_state" in resp.headers["location"]
