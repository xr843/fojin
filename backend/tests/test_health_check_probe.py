"""Orchestration tests for the source health-probe (retry + SSL re-confirm).

巡检探测的编排逻辑测试：瞬时失败重试、证书链不全的二次确认。Pure logic with
stubbed httpx clients — no real network. The classification rules themselves
live in ``test_source_health.py``; here we test that ``probe`` calls them with
the right inputs and retries the right failures."""

import importlib.util
import pathlib
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from cryptography import x509

from app.services.source_health import HOST_DNS_UNRESOLVED, HOST_NON_PUBLIC, HOST_PUBLIC

# health_check_sources.py is a cron script, not an importable package module —
# load it by path so we can exercise its probe orchestration directly.
_HC_PATH = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "health_check_sources.py"
_spec = importlib.util.spec_from_file_location("health_check_sources", _HC_PATH)
hc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hc)

URL = "https://src.example.org/"

# 证书复核用的固定时间点，避免测试依赖真实时钟。
PAST = datetime.now(UTC) - timedelta(days=30)
FUTURE = datetime.now(UTC) + timedelta(days=200)


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
    monkeypatch.setattr(hc, "classify_host", lambda host: HOST_PUBLIC)
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


# --- 判定要带 confidence，且证书失败必须独立复核 ---------------------------
# 生产实测：42 条非 ok 里 24 条是 timeout/DNS（换个观测点结论可能就变），
# 另有 2 条证书判定与实际证书对不上（www.cnki.net 的叶证书是 *.cnki.net、
# 2027 年才到期，却被记成 Hostname mismatch）。判定必须自带可信度，
# 前台才能只展示站得住的那部分。


async def test_http_status_verdict_is_high_confidence():
    client = FakeClient(FakeResp(404))
    v = await hc.probe(client, FakeClient(), "src", URL)
    assert v["status"] == "degraded"
    assert v["confidence"] == "high"


async def test_timeout_verdict_is_low_confidence(monkeypatch):
    client = FakeClient(httpx.ConnectTimeout("timed out"), httpx.ConnectTimeout("timed out"))
    v = await hc.probe(client, FakeClient(), "src", URL)
    assert v["status"] == "unreachable"
    assert v["confidence"] == "low"


async def test_dns_failure_is_reported_separately_and_low_confidence(monkeypatch):
    # 探测机解析不了 ≠ 站点没了。
    monkeypatch.setattr(hc, "classify_host", lambda host: HOST_DNS_UNRESOLVED)
    v = await hc.probe(FakeClient(), FakeClient(), "src", URL)
    assert v["status"] == "unreachable"
    assert v["confidence"] == "low"
    assert "dns_unresolved" in v["detail"]


async def test_non_public_host_is_high_confidence(monkeypatch):
    # 解析到内网地址是探测机自己就能确定的事实，也正是 SSRF 要拦的。
    monkeypatch.setattr(hc, "classify_host", lambda host: HOST_NON_PUBLIC)
    v = await hc.probe(FakeClient(), FakeClient(), "src", URL)
    assert v["status"] == "unreachable"
    assert v["confidence"] == "high"
    assert "non_public" in v["detail"]


async def test_cert_failure_with_healthy_leaf_is_low_confidence(monkeypatch):
    # CNKI 的情形：握手被拒，但叶证书未过期且覆盖该主机名 → 是观测点的问题。
    monkeypatch.setattr(hc, "_read_leaf_facts", lambda host, port: (FUTURE, ["*.cnki.net", "cnki.net"]))
    client = FakeClient(httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] Hostname mismatch"))
    v = await hc.probe(client, FakeClient(), "src", "https://www.cnki.net/")
    assert v["status"] == "cert_invalid"
    assert v["confidence"] == "low"
    assert "looks_valid" in v["detail"]


async def test_cert_failure_with_expired_leaf_is_high_confidence(monkeypatch):
    # 台大的情形：叶证书确实已过期，全网一致，可以放心报出去。
    monkeypatch.setattr(hc, "_read_leaf_facts", lambda host, port: (PAST, ["www.example.org"]))
    client = FakeClient(httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate has expired"))
    v = await hc.probe(client, FakeClient(), "src", URL)
    assert v["status"] == "cert_invalid"
    assert v["confidence"] == "high"
    assert "expired" in v["detail"]


async def test_cert_failure_with_unreadable_leaf_is_low_confidence(monkeypatch):
    # 服务器在发证书前就掐断握手（TLSV1_ALERT_INTERNAL_ERROR）：无从复核。
    monkeypatch.setattr(hc, "_read_leaf_facts", lambda host, port: (None, []))
    client = FakeClient(httpx.ConnectError("[SSL: TLSV1_ALERT_INTERNAL_ERROR] internal error"))
    v = await hc.probe(client, FakeClient(), "src", URL)
    assert v["status"] == "cert_invalid"
    assert v["confidence"] == "low"


async def test_ok_verdict_is_high_confidence():
    v = await hc.probe(FakeClient(FakeResp(200)), FakeClient(), "src", URL)
    assert v["status"] == "ok"
    assert v["confidence"] == "high"


# --- 叶证书解析：拿真证书验，别只验 mock ---------------------------------
# 判定逻辑此前只在 _read_leaf_facts 被 mock 的情况下测过，等于没验证过
# cryptography 的 API 用法（not_valid_after_utc 是 42+ 才有的属性）。


def _self_signed(not_after, san_names):
    """一张自签证书，只用来喂解析函数 —— 不联网、不信任。"""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "leaf.example")])
    builder = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_after - timedelta(days=365))
        .not_valid_after(not_after)
    )
    if san_names:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(n) for n in san_names]), critical=False
        )
    cert = builder.sign(key, hashes.SHA256())
    return cert.public_bytes(serialization.Encoding.DER)


def test_leaf_facts_reads_not_after_and_sans():
    der = _self_signed(FUTURE.replace(microsecond=0), ["*.cnki.net", "cnki.net"])
    not_after, san = hc.leaf_facts_from_der(der)
    assert not_after is not None
    assert not_after.tzinfo is not None, "classify_cert 拿它和 aware 的 now 比较，必须带时区"
    assert abs((not_after - FUTURE).total_seconds()) < 2
    assert san == ["*.cnki.net", "cnki.net"]


def test_leaf_facts_without_san_extension():
    der = _self_signed(FUTURE.replace(microsecond=0), [])
    not_after, san = hc.leaf_facts_from_der(der)
    assert not_after is not None
    assert san == []


def test_leaf_facts_on_garbage_is_unknown():
    assert hc.leaf_facts_from_der(b"not a certificate") == (None, [])
    assert hc.leaf_facts_from_der(b"") == (None, [])


def test_leaf_facts_feed_classify_cert_end_to_end():
    # 解析出来的东西必须能直接喂给 classify_cert —— 这是两者之间唯一的接口。
    from app.services.source_health import CERT_LOOKS_VALID, classify_cert

    der = _self_signed(FUTURE.replace(microsecond=0), ["*.cnki.net"])
    not_after, san = hc.leaf_facts_from_der(der)
    assert (
        classify_cert(host="www.cnki.net", not_after=not_after, san_dns=san, now=datetime.now(UTC)) == CERT_LOOKS_VALID
    )
