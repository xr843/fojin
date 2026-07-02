"""Orchestration tests for the source health-probe (retry + SSL re-confirm).

巡检探测的编排逻辑测试：瞬时失败重试、证书链不全的二次确认。Pure logic with
stubbed httpx clients — no real network. The classification rules themselves
live in ``test_source_health.py``; here we test that ``probe`` calls them with
the right inputs and retries the right failures."""

import importlib.util
import pathlib

import httpx
import pytest

# health_check_sources.py is a cron script, not an importable package module —
# load it by path so we can exercise its probe orchestration directly.
_HC_PATH = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "health_check_sources.py"
_spec = importlib.util.spec_from_file_location("health_check_sources", _HC_PATH)
hc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hc)

URL = "https://src.example.org/"


class FakeResp:
    def __init__(
        self,
        status_code: int,
        location: str | None = None,
        headers: dict[str, str] | None = None,
        text: str = "",
    ):
        self.status_code = status_code
        self.headers = headers or {}
        if location:
            self.headers["location"] = location
        self.is_redirect = location is not None
        self.text = text


class FakeClient:
    """Yields one scripted outcome (a FakeResp or an exception) per .get()."""

    def __init__(self, *actions):
        self._actions = list(actions)
        self.calls = 0

    async def get(self, url, follow_redirects=False, timeout=None):
        self.calls += 1
        if not self._actions:
            raise AssertionError(f"unexpected extra .get({url})")
        act = self._actions.pop(0)
        if isinstance(act, BaseException):
            raise act
        return act


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    # We test probe orchestration, not the SSRF/DNS guard (covered elsewhere) or
    # the real TLS/AIA handshake: treat every host as public, the leaf as
    # AIA-advertising by default, and drop the retry backoff so tests are fast.
    monkeypatch.setattr(hc, "host_is_public", lambda host: True)
    monkeypatch.setattr(hc, "_leaf_declares_aia_issuer", lambda host, port: True)
    monkeypatch.setattr(hc, "RETRY_BACKOFF", 0)


async def test_incomplete_chain_live_host_with_aia_downgrades_to_ok():
    # Missing intermediate + the host serves content + the leaf advertises an
    # AIA issuer (default patch) -> browsers recover, so no badge.
    client = FakeClient(
        httpx.ConnectError(
            "[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate"
        )
    )
    insecure = FakeClient(FakeResp(200))
    v = await hc.probe(client, insecure, "src", URL)
    assert v["status"] == "ok"
    assert v["detail"] is None
    assert insecure.calls == 1  # the liveness re-confirm fetch happened


async def test_incomplete_chain_without_aia_issuer_stays_cert_invalid(monkeypatch):
    # Same OpenSSL code-20 error, host is live, but the leaf advertises no AIA
    # issuer (a genuinely untrusted root) -> browsers reject -> keep the badge.
    monkeypatch.setattr(hc, "_leaf_declares_aia_issuer", lambda host, port: False)
    client = FakeClient(httpx.ConnectError("unable to get local issuer certificate"))
    insecure = FakeClient(FakeResp(200))
    v = await hc.probe(client, insecure, "src", URL)
    assert v["status"] == "cert_invalid"


async def test_hard_cert_error_stays_cert_invalid_without_reprobe():
    client = FakeClient(httpx.ConnectError("certificate has expired (_ssl.c:1010)"))
    insecure = FakeClient()  # must NOT be consulted for a hard cert failure
    v = await hc.probe(client, insecure, "src", URL)
    assert v["status"] == "cert_invalid"
    assert insecure.calls == 0


async def test_incomplete_chain_but_dead_host_stays_cert_invalid():
    # Chain gap, but the insecure re-fetch also fails — don't launder to ok.
    client = FakeClient(httpx.ConnectError("unable to get local issuer certificate"))
    insecure = FakeClient(httpx.ConnectError("connection reset"))
    v = await hc.probe(client, insecure, "src", URL)
    assert v["status"] == "cert_invalid"
    assert insecure.calls == 1


async def test_timeout_then_success_on_retry_is_ok():
    client = FakeClient(httpx.TimeoutException("timed out"), FakeResp(200))
    v = await hc.probe(client, FakeClient(), "src", URL)
    assert v["status"] == "ok"
    assert client.calls == 2  # original probe + one retry


async def test_persistent_timeout_is_unreachable():
    client = FakeClient(httpx.TimeoutException("t1"), httpx.TimeoutException("t2"))
    v = await hc.probe(client, FakeClient(), "src", URL)
    assert v["status"] == "unreachable"
    assert v["detail"].startswith("timeout")
    assert client.calls == 2


async def test_5xx_then_200_on_retry_is_ok():
    client = FakeClient(FakeResp(502), FakeResp(200))
    v = await hc.probe(client, FakeClient(), "src", URL)
    assert v["status"] == "ok"
    assert client.calls == 2


async def test_cloudflare_challenge_503_is_ok_without_retry():
    client = FakeClient(FakeResp(503, headers={"cf-mitigated": "challenge"}))
    v = await hc.probe(client, FakeClient(), "src", URL)
    assert v["status"] == "ok"
    assert client.calls == 1


async def test_stable_404_is_degraded_and_not_retried():
    client = FakeClient(FakeResp(404))
    v = await hc.probe(client, FakeClient(), "src", URL)
    assert v["status"] == "degraded"
    assert client.calls == 1  # a 4xx is a stable verdict — no retry


async def test_cross_domain_redirect_is_moved():
    client = FakeClient(FakeResp(301, location="https://newsite.example.net/"), FakeResp(200))
    v = await hc.probe(client, FakeClient(), "src", URL)
    assert v["status"] == "moved"
    assert v["detail"] == "https://newsite.example.net/"


async def test_missing_url_is_skipped():
    v = await hc.probe(FakeClient(), FakeClient(), "src", None)
    assert v["status"] is None  # no verdict invented for an absent base_url
