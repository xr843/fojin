"""Unit tests for data-source health classification.

数据源健康状态分类的单元测试。Pure logic, no DB / network."""

import importlib.util
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.services.source_health import (
    CERT_EXPIRED,
    CERT_HOSTNAME_MISMATCH,
    CERT_LOOKS_VALID,
    CERT_UNKNOWN,
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    HOST_DNS_UNRESOLVED,
    HOST_NON_PUBLIC,
    HOST_PUBLIC,
    SSL_CHAIN_INCOMPLETE,
    SSL_ERROR,
    _ip_is_blocked,
    classify_cert,
    classify_health,
    classify_host,
    host_is_public,
    is_incomplete_chain_error,
    probe_confidence,
    resolve_unreachable_since,
)

HOME = "https://example.org/"


def test_plain_2xx_same_site_is_ok():
    assert classify_health(error=None, status_code=200, requested_url=HOME, final_url=HOME) == "ok"


def test_redirect_within_same_host_is_ok():
    # Sites reorganise paths; a path-only redirect is not a "move".
    assert (
        classify_health(
            error=None, status_code=200, requested_url=HOME, final_url="https://example.org/welcome"
        )
        == "ok"
    )


def test_http_to_https_upgrade_is_ok():
    assert (
        classify_health(
            error=None, status_code=200, requested_url="http://example.org/", final_url=HOME
        )
        == "ok"
    )


def test_www_prefix_difference_is_ok():
    assert (
        classify_health(
            error=None, status_code=200, requested_url=HOME, final_url="https://www.example.org/"
        )
        == "ok"
    )


def test_redirect_to_different_domain_is_moved():
    assert (
        classify_health(
            error=None, status_code=200, requested_url=HOME, final_url="https://newsite.com/"
        )
        == "moved"
    )


def test_subdomain_restructure_within_same_site_is_not_moved():
    # read.84000.co -> 84000.co, collections.vam.ac.uk -> vam.ac.uk: a
    # sub-domain restructure by the same operator is not an actionable move.
    for requested, final in [
        ("https://read.84000.co/x", "https://84000.co/"),
        ("https://collections.vam.ac.uk/", "https://www.vam.ac.uk/collections"),
        ("https://www.univie.ac.at/tocharian/", "https://cetom.univie.ac.at/"),
    ]:
        assert (
            classify_health(
                error=None, status_code=200, requested_url=requested, final_url=final
            )
            == "ok"
        )


def test_404_and_410_are_degraded():
    # Only "page is genuinely gone" codes count as degraded.
    for code in (404, 410):
        assert (
            classify_health(error=None, status_code=code, requested_url=HOME, final_url=HOME)
            == "degraded"
        )


def test_other_4xx_is_ok():
    # 401 auth / 403 bot-or-geo-block / 429 rate-limit: the server answered,
    # the site is up — it just won't serve an automated probe.
    for code in (400, 401, 403, 429):
        assert (
            classify_health(error=None, status_code=code, requested_url=HOME, final_url=HOME)
            == "ok"
        )


def test_5xx_is_unreachable():
    for code in (500, 502, 503):
        assert (
            classify_health(error=None, status_code=code, requested_url=HOME, final_url=HOME)
            == "unreachable"
        )


def test_cloudflare_challenge_response_is_ok():
    # A Cloudflare challenge means the site is reachable but the bot probe is
    # blocked; it should not start an unreachable streak.
    assert (
        classify_health(
            error=None,
            status_code=503,
            requested_url=HOME,
            final_url=HOME,
            response_headers={"Cf-Mitigated": "challenge"},
        )
        == "ok"
    )


def test_ssl_error_is_cert_invalid():
    assert (
        classify_health(error="ssl", status_code=None, requested_url=HOME, final_url=None)
        == "cert_invalid"
    )


def test_ssl_chain_incomplete_is_ok():
    # A missing-intermediate chain gap, already confirmed content-reachable by
    # the probe's insecure re-fetch: AIA-fetching browsers load it, so no badge.
    assert (
        classify_health(
            error="ssl_chain_incomplete", status_code=None, requested_url=HOME, final_url=None
        )
        == "ok"
    )


@pytest.mark.parametrize(
    "msg",
    [
        "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to "
        "get local issuer certificate (_ssl.c:1010)",
        "unable to get local issuer certificate",
        "UNABLE TO GET LOCAL ISSUER CERTIFICATE",  # case-insensitive
    ],
)
def test_incomplete_chain_messages_detected(msg):
    assert is_incomplete_chain_error(msg) is True


@pytest.mark.parametrize(
    "msg",
    [
        "certificate has expired",
        "Hostname mismatch, certificate is not valid for 'example.org'",
        "self-signed certificate",
        "self-signed certificate in certificate chain",  # private root -> hard fail
        "EE certificate key too weak",
        "no alternative certificate subject name matches target host name",
        "tlsv1 alert internal error",
        "",
        None,
    ],
)
def test_hard_cert_errors_are_not_incomplete_chain(msg):
    assert is_incomplete_chain_error(msg) is False


def test_timeout_and_connect_errors_are_unreachable():
    for err in ("timeout", "connect", "redirect_loop", "other"):
        assert (
            classify_health(error=err, status_code=None, requested_url=HOME, final_url=None)
            == "unreachable"
        )


def test_moved_classification_ignores_error_status_codes():
    # A cross-domain redirect that lands on a 404 is still primarily "moved":
    # the domain change is the more actionable signal for an editor.
    assert (
        classify_health(
            error=None, status_code=404, requested_url=HOME, final_url="https://newsite.com/gone"
        )
        == "moved"
    )


@pytest.mark.parametrize("status", [200, 301, 302, 399])
def test_2xx_3xx_range_treated_as_reachable(status):
    assert classify_health(
        error=None, status_code=status, requested_url=HOME, final_url=HOME
    ) == "ok"


def test_no_final_url_with_2xx_is_ok():
    # A clean status with no final_url (no redirect observed) is not a "move".
    assert classify_health(error=None, status_code=200, requested_url=HOME, final_url=None) == "ok"


# ---- SSRF guard: IP / host classification ----


@pytest.mark.parametrize(
    "ip",
    [
        "10.0.0.1",  # private
        "192.168.1.1",  # private
        "172.16.0.1",  # private
        "127.0.0.1",  # loopback
        "169.254.169.254",  # link-local (cloud metadata)
        "0.0.0.0",  # unspecified
        "224.0.0.1",  # multicast
        "::1",  # IPv6 loopback
        "fe80::1",  # IPv6 link-local
        "not-an-ip",  # unparseable -> fail closed
    ],
)
def test_ip_is_blocked_rejects_non_public(ip):
    assert _ip_is_blocked(ip) is True


@pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1", "2001:4860:4860::8888"])
def test_ip_is_blocked_allows_public(ip):
    assert _ip_is_blocked(ip) is False


def test_host_is_public_rejects_loopback_and_metadata():
    # IP literals resolve through getaddrinfo without a DNS lookup.
    assert host_is_public("127.0.0.1") is False
    assert host_is_public("169.254.169.254") is False
    assert host_is_public("localhost") is False


def test_host_is_public_allows_public_ip_literal():
    assert host_is_public("8.8.8.8") is True


def test_host_is_public_rejects_empty():
    assert host_is_public(None) is False
    assert host_is_public("") is False


# --- resolve_unreachable_since: streak tracking ---------------------------

NOW = datetime(2026, 5, 19, 4, 30, tzinfo=UTC)
EARLIER = NOW - timedelta(days=12)


def test_unreachable_streak_starts_when_newly_unreachable():
    # No prior streak -> the streak starts now.
    assert resolve_unreachable_since("unreachable", None, NOW) == NOW


def test_unreachable_streak_start_is_preserved_while_still_unreachable():
    # An ongoing streak keeps its original start, so age keeps accruing.
    assert resolve_unreachable_since("unreachable", EARLIER, NOW) == EARLIER


@pytest.mark.parametrize("status", ["ok", "degraded", "cert_invalid", "moved"])
def test_any_non_unreachable_status_clears_the_streak(status):
    # "30 consecutive days unreachable" is about connectivity specifically —
    # every other verdict, healthy or not, ends the streak.
    assert resolve_unreachable_since(status, EARLIER, NOW) is None


def test_non_unreachable_with_no_prior_streak_stays_none():
    assert resolve_unreachable_since("ok", None, NOW) is None


def test_streak_start_is_timezone_aware():
    # The value lands in a TIMESTAMPTZ column — a naive datetime would shift.
    assert resolve_unreachable_since("unreachable", None, NOW).tzinfo is not None


# --- migration 0166 sanity -------------------------------------------------


def _load_migration(path: Path):
    spec = importlib.util.spec_from_file_location("migration_0166", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0166_migration_keeps_source_health_update_narrow():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0166_fix_source_urls_and_health_false_positives.py"
    )
    assert migration_path.exists()
    migration = _load_migration(migration_path)

    assert migration.revision == "0166"
    assert migration.down_revision == "0165"
    assert migration.INDICA_BUDDHICA_URL == "https://indica-et-buddhica.com/"
    assert migration.CLEAR_HEALTH_CODES == ("indica-buddhica-repo",)
    assert migration.GRETIL_DISTRIBUTION_UPDATE["url"] == (
        "https://gretil.sub.uni-goettingen.de/gretil.html"
    )
    assert "not a hard dependency for scripts/archive/imports/import_gretil.py" in (
        migration.GRETIL_DISTRIBUTION_UPDATE["license_note"]
    )


# --- classify_host: DNS 查不到 ≠ 非公网地址 --------------------------------
# 生产上 42 条非 ok 里有 8 条是「unresolvable or non-public host」，把「探测机
# 解析不了」和「解析到内网地址」混成了一类。前者往往是探测点的网络问题
# （VPS 的 DNS 到不了某些院校域名），后者才是真要拦的 SSRF 目标。


def test_classify_host_non_public_address():
    assert classify_host("127.0.0.1") == HOST_NON_PUBLIC
    assert classify_host("169.254.169.254") == HOST_NON_PUBLIC


def test_classify_host_public_address():
    assert classify_host("8.8.8.8") == HOST_PUBLIC


def test_classify_host_unresolvable_is_its_own_bucket(monkeypatch):
    # 解析失败 ≠ 解析到内网地址。这里必须打桩 getaddrinfo：开发机上的
    # DNS 代理（fake-IP）会把连不存在的域名都答成 198.18.x.x，真去查会
    # 让这条测试在不同机器上给出不同结果。
    def boom(*_args, **_kwargs):
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    assert classify_host("anything.example") == HOST_DNS_UNRESOLVED


def test_classify_host_empty_is_non_public_fail_closed():
    # 空主机名没有可探测的目标，按 SSRF 防线的「fail closed」归到非公网。
    assert classify_host(None) == HOST_NON_PUBLIC
    assert classify_host("") == HOST_NON_PUBLIC


def test_host_is_public_still_fails_closed_for_both_buckets(monkeypatch):
    # SSRF 防线的语义不能松：只有 public 放行，dns_unresolved 也照样拦。
    assert host_is_public("8.8.8.8") is True
    assert host_is_public("127.0.0.1") is False

    def boom(*_args, **_kwargs):
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    assert host_is_public("anything.example") is False


# --- classify_cert: 独立复核证书，别把环境问题当成站点问题 ------------------
# 生产实测：www.cnki.net 的证书是 *.cnki.net、2027 年才到期，探测器却记成
# "Hostname mismatch"；遊方站证书 2026-08 到期，探测器记成 "has expired"。
# 两条都是探测点看到的东西和全网不一致，不该当作站点的毛病报出去。

NOW = datetime(2026, 7, 21, tzinfo=UTC)


def test_classify_cert_expired():
    assert (
        classify_cert(
            host="buddhism.lib.ntu.edu.tw",
            not_after=datetime(2026, 7, 15, tzinfo=UTC),
            san_dns=["buddhism.lib.ntu.edu.tw"],
            now=NOW,
        )
        == CERT_EXPIRED
    )


def test_classify_cert_hostname_mismatch():
    # PTS 巴英辞典实测：证书是 *.stackcp.com，压根不含 palitext.com。
    assert (
        classify_cert(
            host="www.palitext.com",
            not_after=datetime(2027, 1, 4, tzinfo=UTC),
            san_dns=["*.stackcp.com", "stackcp.com"],
            now=NOW,
        )
        == CERT_HOSTNAME_MISMATCH
    )


def test_classify_cert_wildcard_covers_one_label():
    # CNKI 的真实情况：*.cnki.net 覆盖 www.cnki.net，不是 mismatch。
    assert (
        classify_cert(
            host="www.cnki.net",
            not_after=datetime(2027, 3, 9, tzinfo=UTC),
            san_dns=["*.cnki.net", "caj.d.cnki.net"],
            now=NOW,
        )
        == CERT_LOOKS_VALID
    )


def test_classify_cert_wildcard_does_not_span_dots_or_bare_domain():
    # *.cnki.net 既不覆盖 cnki.net 本身，也不覆盖 a.b.cnki.net。
    assert (
        classify_cert(host="cnki.net", not_after=datetime(2027, 3, 9, tzinfo=UTC), san_dns=["*.cnki.net"], now=NOW)
        == CERT_HOSTNAME_MISMATCH
    )
    assert (
        classify_cert(host="a.b.cnki.net", not_after=datetime(2027, 3, 9, tzinfo=UTC), san_dns=["*.cnki.net"], now=NOW)
        == CERT_HOSTNAME_MISMATCH
    )


def test_classify_cert_expiry_wins_over_hostname():
    # 两个毛病都占时，报更硬的那个：过期是全网一致的事实。
    assert (
        classify_cert(host="x.example", not_after=datetime(2020, 1, 1, tzinfo=UTC), san_dns=["other.example"], now=NOW)
        == CERT_EXPIRED
    )


def test_classify_cert_unknown_when_leaf_unavailable():
    # 连证书都取不到（TLSV1_ALERT_INTERNAL_ERROR 那两条），无从复核。
    assert classify_cert(host="x.example", not_after=None, san_dns=[], now=NOW) == CERT_UNKNOWN


# --- probe_confidence: 哪些判定敢放到用户面前 -------------------------------


def test_confidence_high_for_http_status_verdicts():
    # 服务器真的答了一个码，全网一致。
    assert probe_confidence(status="degraded", error=None, cert=None) == CONFIDENCE_HIGH
    assert probe_confidence(status="unreachable", error=None, cert=None) == CONFIDENCE_HIGH


def test_confidence_low_for_every_cert_verdict_however_well_corroborated():
    """证书判词一律不可外推——复读 leaf 和探测走的是同一个点位。

    这条推翻了 0172 的设计。2026-08-15 实测：从新加坡 VPS 正确发送 SNI、链
    校验通过的前提下，www.cnki.net 收到的是 *.cdn.myqcloud.com、
    www.palitext.com 是 *.stackcp.com、cbc.dila.edu.tw 是 dazangthings.nz，
    而换一个点位拿到的都是各站自己的有效证书。「过期」一类同样中招：
    youfun.litphil.sinica.edu.tw 被判过期，别处 leaf 有效期到 2026-10-28。
    所以 leaf 复读只能证明「这个点位被喂了什么」，不能证明站点有问题。
    """
    for cert in (CERT_EXPIRED, CERT_HOSTNAME_MISMATCH, CERT_LOOKS_VALID, CERT_UNKNOWN):
        verdict = probe_confidence(status="cert_invalid", error=SSL_ERROR, cert=cert)
        assert verdict == CONFIDENCE_LOW, f"cert={cert} 不该被当作跨点位证据"


def test_confidence_high_survives_only_for_origin_answered_and_non_public():
    """收窄之后 high 只剩两类，别让谁不小心把证书类再加回来。

    这两类的共同点是「不依赖探测点」：源站自己回了一个状态码，或主机名解析
    进非公网地址（探测机自己就能定的事实，也正是 SSRF 该拦的）。
    """
    for status in ("ok", "degraded", "unreachable"):
        assert probe_confidence(status=status, error=None, cert=None) == CONFIDENCE_HIGH
    assert probe_confidence(status="unreachable", error=HOST_NON_PUBLIC, cert=None) == CONFIDENCE_HIGH
    # 其余一律 low —— 含 0172 曾放行的两种证书判词。
    for err in (SSL_ERROR, SSL_CHAIN_INCOMPLETE, HOST_DNS_UNRESOLVED, "timeout", "connect", "read"):
        assert probe_confidence(status="unreachable", error=err, cert=CERT_EXPIRED) == CONFIDENCE_LOW, err


def test_confidence_low_for_timeout_and_dns():
    assert probe_confidence(status="unreachable", error="timeout", cert=None) == CONFIDENCE_LOW
    assert probe_confidence(status="unreachable", error="connect", cert=None) == CONFIDENCE_LOW
    assert probe_confidence(status="unreachable", error=HOST_DNS_UNRESOLVED, cert=None) == CONFIDENCE_LOW


def test_confidence_high_for_non_public_host():
    # 解析到内网地址是探测机能确定的事实，也是真该拦的。
    assert probe_confidence(status="unreachable", error=HOST_NON_PUBLIC, cert=None) == CONFIDENCE_HIGH


def test_confidence_high_for_ok():
    assert probe_confidence(status="ok", error=None, cert=None) == CONFIDENCE_HIGH


def test_0172_migration_adds_health_confidence():
    migration_path = (
        Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0172_add_source_health_confidence.py"
    )
    assert migration_path.exists()
    migration = _load_migration(migration_path)

    assert migration.revision == "0172"
    assert migration.down_revision == "0171"
