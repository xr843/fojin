"""Probe every active data source and persist its health_status.

巡检所有活跃数据源的可达性，将结果写入 data_sources.health_status /
health_checked_at / health_detail / unreachable_since，并失效 sources 列表缓存。

Designed to run from cron on the deployment host. Independent of ``is_active``:
a source can be reachable-but-deprecated, or down-but-kept.

Redirects are followed manually with a per-hop public-IP check (see
``host_is_public``) so a hijacked source URL cannot turn the probe into an
SSRF against internal services.

Usage:
    cd backend
    python scripts/health_check_sources.py            # probe + write
    python scripts/health_check_sources.py --dry-run   # probe + report only
"""

import argparse
import asyncio
import os
import socket
import ssl
import sys
import warnings
from datetime import UTC, datetime
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import redis.asyncio as aioredis
from cryptography import x509
from cryptography.x509.oid import AuthorityInformationAccessOID
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.api.sources import SOURCES_LIST_CACHE_KEY
from app.config import settings
from app.services.source_health import (
    CONFIDENCE_HIGH,
    HOST_PUBLIC,
    SSL_CHAIN_INCOMPLETE,
    SSL_ERROR,
    VALID_STATUSES,
    classify_cert,
    classify_health,
    classify_host,
    is_incomplete_chain_error,
    probe_confidence,
    resolve_unreachable_since,
)

TIMEOUT = 30  # seconds per request — small academic/library sites are often slow
CONCURRENCY = 10  # max concurrent probes — be gentle on small academic sites
MAX_REDIRECTS = 5  # redirect hops to follow before giving up
# A single probe from one VPS vantage is noisy: a transient timeout, a dropped
# connection or a 5xx blip would otherwise badge a healthy source. Retry those
# (and only those) once before recording a verdict.
RETRY_BACKOFF = 2  # seconds to wait before the single retry of a transient fail
USER_AGENT = "Mozilla/5.0 (compatible; FoJin-HealthCheck/1.0; +https://fojin.app)"


def _error_kind(exc: Exception) -> str:
    """Map an httpx exception to a source_health error token."""
    if isinstance(exc, httpx.TooManyRedirects):
        return "redirect_loop"
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.ConnectError):
        # httpx has no dedicated SSL exception; certificate failures surface as
        # ConnectError with an SSL-flavoured message.
        msg = str(exc).lower()
        if "ssl" in msg or "certificate" in msg or "tls" in msg:
            return SSL_ERROR
        return "connect"
    return "other"


# data_sources.health_detail is VARCHAR(500); Postgres errors (not truncates)
# on an over-long value, which would abort the whole write transaction. Cap
# every detail at the boundary so one pathological redirect URL can't do that.
HEALTH_DETAIL_MAXLEN = 500


def _verdict(
    code: str,
    status: str | None,
    detail: str | None,
    confidence: str = CONFIDENCE_HIGH,
) -> dict:
    """A probe result. ``detail`` is the storage-ready health_detail value:
    the redirect target for ``moved``, the failure reason otherwise, ``None``
    for ``ok`` (and for skipped probes, where ``status`` is also ``None``).

    ``confidence`` says whether the verdict holds beyond this prober's vantage
    — see :func:`app.services.source_health.probe_confidence`. Only ``high``
    verdicts are safe to present as a fault of the source itself. It defaults to
    ``high`` because the paths that do not pass it (skipped probes, malformed
    URLs, redirect-budget exhaustion) are all conclusions the prober reaches
    from the stored config alone, with no network ambiguity.

    ``detail`` is hard-capped to the column width — see HEALTH_DETAIL_MAXLEN."""
    if detail is not None and len(detail) > HEALTH_DETAIL_MAXLEN:
        detail = detail[: HEALTH_DETAIL_MAXLEN - 1] + "…"
    return {"code": code, "status": status, "detail": detail, "confidence": confidence}


def leaf_facts_from_der(der: bytes) -> tuple[datetime | None, list[str]]:
    """Parse a DER leaf into its ``notAfter`` and dNSName SANs.

    Split out from the socket work above so the parsing — the part that depends
    on the ``cryptography`` API surface — is unit-testable against a real
    certificate without a network. Returns ``(None, [])`` for anything
    unparseable, i.e. "could not re-check"."""
    if not der:
        return None, []
    try:
        cert = x509.load_der_x509_certificate(der)
    except Exception:
        return None, []
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(
            x509.DNSName
        )
    except x509.ExtensionNotFound:
        san = []
    return cert.not_valid_after_utc, list(san)


def _read_leaf_facts(host: str, port: int) -> tuple[datetime | None, list[str]]:
    """The leaf certificate's ``notAfter`` and dNSName SANs, or ``(None, [])``.

    Read with verification disabled so the cert is legible even when the chain
    does not validate — it is inspected, never trusted. This is what lets
    :func:`classify_cert` re-derive a verdict from the certificate itself rather
    than from whatever OpenSSL made of the handshake on this particular host,
    which is how a healthy source (leaf valid, hostname covered) stops being
    badged over a vantage-specific TLS failure.

    Any failure returns ``(None, [])`` — "could not re-check", which downgrades
    confidence rather than inventing a verdict. Blocking socket/TLS work; call
    via ``asyncio.to_thread``."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with (
            socket.create_connection((host, port), timeout=TIMEOUT) as sock,
            ctx.wrap_socket(sock, server_hostname=host) as ssock,
        ):
            der = ssock.getpeercert(binary_form=True)
    except Exception:
        return None, []
    return leaf_facts_from_der(der)


async def _cert_recheck(url: str) -> str:
    """Re-derive the cert verdict for ``url``'s host from the leaf itself."""
    parts = urlsplit(url)
    if not parts.hostname:
        return classify_cert(host="", not_after=None, san_dns=[], now=datetime.now(UTC))
    not_after, san = await asyncio.to_thread(_read_leaf_facts, parts.hostname, parts.port or 443)
    return classify_cert(host=parts.hostname, not_after=not_after, san_dns=san, now=datetime.now(UTC))


async def _serves_content(client: httpx.AsyncClient, url: str) -> bool:
    """True when ``url``'s host returns any non-5xx response with cert
    verification disabled.

    Used only to confirm that a source which failed the verified probe with a
    *missing-intermediate* cert error is nonetheless live — so a chain gap
    (which AIA browsers paper over) downgrades to ``ok`` instead of a dead host
    being badged healthy. ``follow_redirects=False`` preserves the SSRF
    guarantee: the caller already vetted this exact host with
    :func:`host_is_public`, and an unvetted redirect target is never chased."""
    try:
        resp = await client.get(url, follow_redirects=False, timeout=TIMEOUT)
        return resp.status_code < 500
    except Exception:
        return False


def _leaf_declares_aia_issuer(host: str, port: int) -> bool:
    """True when the server's leaf certificate carries an AIA caIssuers URL.

    This is the signal that separates a *recoverable* missing-intermediate chain
    — AIA-capable browsers (Chrome/Edge/Safari) fetch the named issuer and
    complete the chain — from a genuinely untrusted leaf (e.g. a private root
    with no AIA), which yields the same OpenSSL "unable to get local issuer"
    code yet every browser rejects. The handshake runs with verification
    disabled so the presented leaf can be read even when the chain doesn't
    validate; the cert is only inspected, never trusted.

    Any failure (connect error, no peer cert, no AIA extension, parse error)
    returns False — the conservative answer that keeps the source cert_invalid.
    Blocking socket/TLS work; call via ``asyncio.to_thread``."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with (
            socket.create_connection((host, port), timeout=TIMEOUT) as sock,
            ctx.wrap_socket(sock, server_hostname=host) as ssock,
        ):
            der = ssock.getpeercert(binary_form=True)
        if not der:
            return False
        cert = x509.load_der_x509_certificate(der)
        aia = cert.extensions.get_extension_for_class(x509.AuthorityInformationAccess).value
        return any(
            desc.access_method == AuthorityInformationAccessOID.CA_ISSUERS for desc in aia
        )
    except Exception:
        return False


async def _chain_gap_is_browser_recoverable(
    insecure_client: httpx.AsyncClient, url: str
) -> bool:
    """True when a missing-intermediate TLS failure is one browsers recover from.

    Both conditions are required, so neither a dead host nor a genuinely
    untrusted leaf is laundered into ``ok``:
      - the host actually serves content (insecure re-fetch, non-5xx) — it's a
        live source, not a host that merely failed at the TLS layer;
      - the leaf certificate declares an AIA caIssuers URL — AIA-capable
        browsers can fetch the absent intermediate and complete the chain."""
    if not await _serves_content(insecure_client, url):
        return False
    parts = urlsplit(url)
    if not parts.hostname:
        return False
    return await asyncio.to_thread(_leaf_declares_aia_issuer, parts.hostname, parts.port or 443)


async def _probe_once(
    client: httpx.AsyncClient, insecure_client: httpx.AsyncClient, code: str, url: str
) -> tuple[dict, bool]:
    """Probe ``url`` once into a ``(verdict, transient)`` pair.

    ``transient`` is True for failures a retry might clear — a timeout, a
    dropped connection, or a 5xx — so the caller can re-probe before recording
    a verdict. A missing-intermediate cert that the insecure re-fetch confirms
    is live downgrades to ``ok`` (see :func:`_serves_content`); every other cert
    failure stays ``cert_invalid``.

    Redirects are followed by hand (``follow_redirects=False``) so every hop's
    host can be vetted with :func:`host_is_public` before a request is sent —
    this is what stops a redirect chain from reaching internal services."""
    current = url
    try:
        for _ in range(MAX_REDIRECTS + 1):
            host = urlsplit(current).hostname
            reachability = classify_host(host)
            if reachability != HOST_PUBLIC:
                # Refuse to probe. Both buckets end as "unreachable" from an
                # editor's view, but they are not equally trustworthy: a name
                # that resolves into non-public space is a fact this prober
                # established (and the SSRF target the guard exists for), while
                # a DNS failure on a single VPS routinely says nothing about the
                # site. Keep them distinct in the detail and in the confidence.
                status = classify_health(
                    error=reachability, status_code=None, requested_url=url, final_url=None
                )
                return (
                    _verdict(
                        code,
                        status,
                        f"{reachability}: {host}",
                        probe_confidence(status=status, error=reachability, cert=None),
                    ),
                    False,
                )
            resp = await client.get(current, follow_redirects=False, timeout=TIMEOUT)
            if resp.is_redirect and "location" in resp.headers:
                current = str(httpx.URL(current).join(resp.headers["location"]))
                continue
            status = classify_health(
                error=None,
                status_code=resp.status_code,
                requested_url=url,
                final_url=current,
                response_headers=resp.headers,
                response_text=getattr(resp, "text", "")[:4096]
                if resp.status_code >= 400
                else None,
            )
            if status == "ok":
                detail = None
            elif status == "moved":
                # The redirect target — the one piece of actionable context.
                # Stored and shown as plain text only; if it is ever turned
                # into an href, the scheme must be sanitised first (a source
                # could redirect to a javascript: / data: Location).
                detail = current
            else:
                detail = f"HTTP {resp.status_code}"
            # A 5xx is the one HTTP outcome worth retrying; ok / moved / degraded
            # and the 4xx the classifier already reads as reachable are stable.
            return _verdict(code, status, detail), status == "unreachable" and resp.status_code >= 500

        # Redirect budget exhausted.
        status = classify_health(
            error="redirect_loop", status_code=None, requested_url=url, final_url=None
        )
        return (
            _verdict(
                code,
                status,
                f"exceeded {MAX_REDIRECTS} redirect hops",
                probe_confidence(status=status, error="redirect_loop", cert=None),
            ),
            False,
        )
    except Exception as exc:  # every probe failure maps to a health verdict
        kind = _error_kind(exc)
        if (
            kind == SSL_ERROR
            and is_incomplete_chain_error(str(exc))
            and await _chain_gap_is_browser_recoverable(insecure_client, current)
        ):
            # Missing-intermediate chain on a live host whose leaf advertises an
            # AIA issuer — AIA-capable browsers complete the chain and load it.
            status = classify_health(
                error=SSL_CHAIN_INCOMPLETE, status_code=None, requested_url=url, final_url=current
            )
            return _verdict(code, status, None), False
        status = classify_health(error=kind, status_code=None, requested_url=url, final_url=None)
        # A rejected handshake is not by itself evidence the *site* is broken:
        # re-read the leaf and see whether the certificate is actually expired
        # or actually issued for another name. When it checks out, the fault is
        # local to this vantage and the verdict drops to low confidence.
        cert = await _cert_recheck(current) if kind == SSL_ERROR else None
        detail = f"{kind}: {str(exc)[:160]}"
        if cert is not None:
            detail = f"{detail} [leaf: {cert}]"
        return (
            _verdict(code, status, detail, probe_confidence(status=status, error=kind, cert=cert)),
            kind in ("timeout", "connect"),
        )


async def probe(
    client: httpx.AsyncClient, insecure_client: httpx.AsyncClient, code: str, url: str | None
) -> dict:
    """Probe one source into a {code, status, detail} verdict, retrying once on
    a transient failure (timeout / dropped connection / 5xx)."""
    if not url or url == "None":
        # No URL to probe — leave it as-is rather than inventing a verdict.
        return _verdict(code, None, "no base_url")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        # A malformed base_url is a config error, not a reachability verdict.
        return _verdict(code, None, f"bad base_url: {url[:80]}")

    verdict, transient = await _probe_once(client, insecure_client, code, url)
    if transient:
        await asyncio.sleep(RETRY_BACKOFF)
        verdict, _ = await _probe_once(client, insecure_client, code, url)
    return verdict


async def main(dry_run: bool) -> None:
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT code, base_url, unreachable_since FROM data_sources "
                    "WHERE is_active = true ORDER BY code"
                )
            )
        ).fetchall()

    # Streak start per source, read once up front: resolve_unreachable_since
    # needs the prior value to decide whether to start, keep or clear the streak.
    prev_unreachable: dict[str, datetime | None] = {r[0]: r[2] for r in rows}

    print(
        f"Health-checking {len(rows)} active sources "
        f"(concurrency={CONCURRENCY}, timeout={TIMEOUT}s, dry_run={dry_run})...\n"
    )

    semaphore = asyncio.Semaphore(CONCURRENCY)
    # verify=True is intentional — detecting cert_invalid is a goal of this job.
    # The insecure client is used *only* to re-confirm a missing-intermediate
    # source is live (see _serves_content); it never produces a verdict on its
    # own, so a real cert failure can't be laundered into "ok".
    async with (
        httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, verify=True) as client,
        httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, verify=False) as insecure_client,
    ):

        async def bounded(code: str, url: str | None) -> dict:
            async with semaphore:
                return await probe(client, insecure_client, code, url)

        results = await asyncio.gather(*(bounded(r[0], r[1]) for r in rows))

    verdicts = [r for r in results if r["status"] is not None]
    skipped = [r for r in results if r["status"] is None]

    # Guard against a logic regression writing an unknown token: classify_health
    # only ever returns VALID_STATUSES, but a bad value would land silently in
    # the DB (the frontend badge lookup fails open to "no badge").
    bad = [r for r in verdicts if r["status"] not in VALID_STATUSES]
    if bad:
        raise SystemExit(f"ABORT: classifier produced invalid status(es): {bad}")

    # ---- write back ----
    changed = 0
    if not dry_run:
        # One timestamp for the whole pass: every row's health_checked_at and
        # any freshly-started unreachable streak share the same probe time.
        checked_at = datetime.now(UTC)
        async with async_session() as session:
            for r in verdicts:
                unreachable_since = resolve_unreachable_since(
                    r["status"], prev_unreachable.get(r["code"]), checked_at
                )
                res = await session.execute(
                    text(
                        "UPDATE data_sources "
                        "SET health_status = :s, health_checked_at = :t, "
                        "    health_detail = :d, health_confidence = :f, "
                        "    unreachable_since = :u "
                        "WHERE code = :c AND is_active = true"
                    ),
                    {
                        "s": r["status"],
                        "t": checked_at,
                        "d": r["detail"],
                        "f": r["confidence"],
                        "u": unreachable_since,
                        "c": r["code"],
                    },
                )
                changed += res.rowcount or 0
            await session.commit()
        if changed != len(verdicts):
            # A source deactivated between the SELECT and the UPDATE drops out.
            print(f"NOTE: {len(verdicts) - changed} verdict(s) not written (source deactivated?).")

    await engine.dispose()

    # ---- bust the sources list cache so the UI badge reflects new verdicts ----
    # delete() runs after commit() so a concurrent reader can only ever
    # re-cache fresh data; only .delete() is used, so no decode_responses.
    if not dry_run and verdicts:
        try:
            redis_client = aioredis.from_url(settings.redis_url)
            await redis_client.delete(SOURCES_LIST_CACHE_KEY)
            await redis_client.aclose()
            print(f"Invalidated cache key '{SOURCES_LIST_CACHE_KEY}'.")
        except Exception as exc:  # cache bust is best-effort
            print(f"WARNING: could not invalidate sources cache: {exc}")

    # ---- report ----
    by_status: dict[str, list[dict]] = {}
    for r in verdicts:
        by_status.setdefault(r["status"], []).append(r)

    for status in ("moved", "cert_invalid", "unreachable", "degraded", "ok"):
        bucket = by_status.get(status, [])
        if not bucket:
            continue
        print(f"{'=' * 70}\n{status.upper()} ({len(bucket)})\n{'=' * 70}")
        for r in sorted(bucket, key=lambda x: x["code"]):
            print(f"  {r['code']:36s} {r['detail'] or ''}")
        print()

    if skipped:
        print(f"SKIPPED — no base_url ({len(skipped)}): {', '.join(s['code'] for s in skipped)}\n")

    problems = sum(len(by_status.get(s, [])) for s in ("moved", "cert_invalid", "unreachable", "degraded"))
    print(
        f"SUMMARY: {len(verdicts)} probed, {len(by_status.get('ok', []))} ok, "
        f"{problems} need attention, {len(skipped)} skipped. "
        f"{'(dry-run, nothing written)' if dry_run else f'{changed} rows updated.'}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Probe data-source health and persist verdicts.")
    parser.add_argument("--dry-run", action="store_true", help="probe and report without writing")
    args = parser.parse_args()
    warnings.filterwarnings("ignore", message="Unverified HTTPS request")
    asyncio.run(main(args.dry_run))
