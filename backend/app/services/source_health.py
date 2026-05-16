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
from urllib.parse import urlsplit

# Probe error kinds the caller may report. Anything that is not a clean HTTP
# response with a status code falls into one of these.
SSL_ERROR = "ssl"

VALID_STATUSES = frozenset({"ok", "degraded", "cert_invalid", "unreachable", "moved"})


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


def classify_health(
    *,
    error: str | None,
    status_code: int | None,
    requested_url: str,
    final_url: str | None,
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

    Returns:
        One of :data:`VALID_STATUSES`.
    """
    if error == SSL_ERROR:
        return "cert_invalid"
    if error is not None:
        return "unreachable"

    # A cross-domain redirect is the most actionable editorial signal — surface
    # it even if the new domain itself answered with an error status.
    if _is_moved(requested_url, final_url):
        return "moved"

    if status_code is None:
        return "unreachable"
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
