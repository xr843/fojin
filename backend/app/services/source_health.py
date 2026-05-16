"""Health-state classification for external data sources.

外部数据源的健康状态分类逻辑。

`health_status` (column on ``data_sources``) is the cron-updated reachability
signal, independent of ``is_active`` (which is editorial removal). This module
holds the pure classification logic so it can be unit-tested without network
or DB; the probing/IO lives in ``scripts/health_check_sources.py``.

Valid statuses: ok | degraded | cert_invalid | unreachable | moved
"""

from urllib.parse import urlsplit

# Probe error kinds the caller may report. Anything that is not a clean HTTP
# response with a status code falls into one of these.
SSL_ERROR = "ssl"

VALID_STATUSES = frozenset({"ok", "degraded", "cert_invalid", "unreachable", "moved"})


def _registrable_host(url: str | None) -> str:
    """Return a normalised host for same-site comparison.

    Lower-cased, leading ``www.`` stripped. Returns ``""`` when the URL has no
    host (so two host-less URLs never compare equal to a real host)."""
    if not url:
        return ""
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _is_moved(requested_url: str, final_url: str | None) -> bool:
    """True when a redirect landed on a different registrable host.

    Path-only redirects, http→https upgrades and www-prefix changes are *not*
    moves — sites reorganise constantly and those are not actionable."""
    if not final_url:
        return False
    src = _registrable_host(requested_url)
    dst = _registrable_host(final_url)
    return bool(src) and bool(dst) and src != dst


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
    if status_code >= 400:
        return "degraded"
    return "ok"
