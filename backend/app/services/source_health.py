"""Health-state classification for external data sources.

外部数据源的健康状态分类逻辑。

`health_status` (column on ``data_sources``) is the cron-updated reachability
signal, independent of ``is_active`` (which is editorial removal). This module
holds the pure classification logic so it can be unit-tested without network
or DB; the probing/IO lives in ``scripts/health_check_sources.py``.

Valid statuses: ok | degraded | cert_invalid | unreachable | moved
"""

import ipaddress
import socket
from collections.abc import Mapping
from datetime import datetime
from urllib.parse import urlsplit

# Probe error kinds the caller may report. Anything that is not a clean HTTP
# response with a status code falls into one of these.
SSL_ERROR = "ssl"
# A cert chain that is merely *incomplete* — the server omitted an intermediate
# certificate ("unable to get local issuer certificate"). AIA-fetching browsers
# (Chrome/Edge/Safari, the large majority of readers) complete the chain and
# load the page normally, so this is not worth a "证书异常" badge. The probe
# assigns this token only after confirming both that the host serves content and
# that the leaf advertises an AIA caIssuers URL — so a genuinely untrusted root,
# which raises the same OpenSSL error, is not downgraded. See
# scripts/health_check_sources.py.
SSL_CHAIN_INCOMPLETE = "ssl_chain_incomplete"

VALID_STATUSES = frozenset({"ok", "degraded", "cert_invalid", "unreachable", "moved"})


def is_incomplete_chain_error(message: str | None) -> bool:
    """True for the *missing-intermediate* TLS family — OpenSSL's "unable to get
    local issuer certificate" (verify code 20).

    This is a coarse pre-filter, not a final verdict. Code 20 covers two cases:
    a server that merely omitted an intermediate (AIA-capable browsers refetch
    it and load the page) and, less commonly, a leaf signed by a CA absent from
    every trust store with no AIA pointer (browsers reject it). The caller only
    downgrades to ``ok`` after a second check confirms the leaf actually
    advertises an AIA caIssuers URL — see ``_chain_gap_is_browser_recoverable``
    in scripts/health_check_sources.py — so this function deliberately stays
    broad. Hard failures with a different signature (expired, hostname mismatch,
    self-signed leaf, weak key, old-TLS alert) never match here and stay
    ``cert_invalid``.
    """
    if not message:
        return False
    return "unable to get local issuer certificate" in message.lower()


def _ip_is_blocked(ip: str) -> bool:
    """True for any non-public address: private, loopback, link-local, etc.

    Unparseable input is treated as blocked (fail closed)."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def host_is_public(host: str | None) -> bool:
    """True only when *every* address ``host`` resolves to is publicly routable.

    The health-check cron follows redirects from admin-editable source URLs on a
    VPS with internal network reach; without this guard a hijacked source could
    redirect the probe at ``169.254.169.254`` (cloud metadata) or an RFC1918
    host — an SSRF. A residual DNS-rebinding window remains between this check
    and httpx's own connect-time resolution; acceptable for a cron over curated
    academic sites, but noted deliberately."""
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError, OSError):
        return False
    return bool(infos) and all(not _ip_is_blocked(info[4][0]) for info in infos)


def _registrable_host(url: str | None) -> str:
    """Return a normalised host for same-site comparison.

    Lower-cased, leading ``www.`` stripped. Returns ``""`` when the URL has no
    host (so two host-less URLs never compare equal to a real host)."""
    if not url:
        return ""
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _same_site(host_a: str, host_b: str) -> bool:
    """True when two hosts belong to the same site.

    Equal hosts, or one a dotted sub-domain of the other — ``read.84000.co``
    and ``84000.co``, ``collections.vam.ac.uk`` and ``vam.ac.uk``. A redirect
    between these is a sub-domain restructure by the same operator, not a move.
    (Sibling sub-domains under a shared parent are *not* caught — telling those
    apart needs a public-suffix list; treating them as moved is the safe miss.)
    """
    if not host_a or not host_b:
        return False
    return (
        host_a == host_b
        or host_a.endswith("." + host_b)
        or host_b.endswith("." + host_a)
    )


def _is_moved(requested_url: str, final_url: str | None) -> bool:
    """True when a redirect landed on a different site.

    Path-only redirects, http→https upgrades, www-prefix changes and
    sub-domain restructures within the same site are *not* moves — sites
    reorganise constantly and those are not actionable."""
    if not final_url:
        return False
    src = _registrable_host(requested_url)
    dst = _registrable_host(final_url)
    if not src or not dst:
        return False
    return not _same_site(src, dst)


def _header_value(headers: Mapping[str, str] | None, name: str) -> str:
    if not headers:
        return ""
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value.strip().lower()
    return ""


def _is_challenge_response(
    status_code: int | None,
    response_headers: Mapping[str, str] | None,
    response_text: str | None,
) -> bool:
    """True when a reachable site returned an anti-bot challenge page."""
    if status_code is None:
        return False
    if _header_value(response_headers, "cf-mitigated") == "challenge":
        return True

    if status_code not in (403, 429, 503):
        return False
    body = (response_text or "").lower()
    if not body:
        return False
    if "/cdn-cgi/challenge-platform" in body or "cf-browser-verification" in body:
        return True
    return "just a moment" in body and "cloudflare" in body


def classify_health(
    *,
    error: str | None,
    status_code: int | None,
    requested_url: str,
    final_url: str | None,
    response_headers: Mapping[str, str] | None = None,
    response_text: str | None = None,
) -> str:
    """Map a single probe outcome to a ``health_status`` value.

    Args:
        error: ``None`` for a clean HTTP response; otherwise the probe error
            kind — ``"ssl"`` for a certificate failure, or any other token
            (``"timeout"``, ``"connect"``, ``"redirect_loop"``, ``"other"``)
            for an unreachable host.
        status_code: final HTTP status, or ``None`` when ``error`` is set.
        requested_url: the URL the probe started from.
        final_url: the URL after following redirects, or ``None``.
        response_headers: final response headers, when a response exists.
        response_text: bounded final response text, used only to recognise
            anti-bot challenge pages that do not expose a dedicated header.

    Returns:
        One of :data:`VALID_STATUSES`.
    """
    if error == SSL_ERROR:
        return "cert_invalid"
    if error == SSL_CHAIN_INCOMPLETE:
        # Only a missing-intermediate chain gap, and the probe already confirmed
        # the host serves content — browsers load it, so no badge.
        return "ok"
    if error is not None:
        return "unreachable"

    # A cross-domain redirect is the most actionable editorial signal — surface
    # it even if the new domain itself answered with an error status.
    if _is_moved(requested_url, final_url):
        return "moved"

    if status_code is None:
        return "unreachable"
    if _is_challenge_response(status_code, response_headers, response_text):
        return "ok"
    if status_code >= 500:
        return "unreachable"
    # Only 404/410 mean the page is genuinely gone — that is a degraded source.
    # Every other 4xx (400 bad-request, 401 auth-required, 403 bot/geo-blocked,
    # 429 rate-limited) means the server answered and the site is up; it just
    # won't serve an automated probe. Treating those as degraded wrongly badges
    # healthy major sources (hathitrust, loc.gov, Cloudflare-fronted sites, …),
    # so they classify as ok — the link still works for a human in a browser.
    if status_code in (404, 410):
        return "degraded"
    return "ok"


def resolve_unreachable_since(
    status: str,
    previous: datetime | None,
    now: datetime,
) -> datetime | None:
    """The ``unreachable_since`` value to persist after a probe.

    ``unreachable_since`` marks when a source *first* entered its current
    continuous unreachable streak. It lets the daily digest flag sources down
    long enough to consider deactivating, without storing per-probe history.
    Any non-``unreachable`` verdict ends the streak — including ``degraded``,
    ``cert_invalid`` and ``moved``, since "30 consecutive days *unreachable*"
    is specifically about connectivity, not any unhealthy state.

      - newly unreachable (``previous`` is None)  -> ``now`` (streak starts)
      - still unreachable (``previous`` is set)   -> ``previous`` (streak kept)
      - any other status                          -> ``None`` (streak cleared)

    The probing/IO caller (``scripts/health_check_sources.py``) is a cron
    singleton and the sole writer of this column, so the read-then-write it
    does around this function carries no concurrency hazard. A source that is
    *skipped* (no probe verdict) is never written, so its streak — like its
    other health columns — freezes at the last probed value.
    """
    if status != "unreachable":
        return None
    return now if previous is None else previous
