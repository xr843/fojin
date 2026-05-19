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
import sys
import warnings
from datetime import UTC, datetime
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.api.sources import SOURCES_LIST_CACHE_KEY
from app.config import settings
from app.services.source_health import (
    SSL_ERROR,
    VALID_STATUSES,
    classify_health,
    host_is_public,
    resolve_unreachable_since,
)

TIMEOUT = 15  # seconds per request
CONCURRENCY = 10  # max concurrent probes — be gentle on small academic sites
MAX_REDIRECTS = 5  # redirect hops to follow before giving up
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


def _verdict(code: str, status: str | None, detail: str | None) -> dict:
    """A probe result. ``detail`` is the storage-ready health_detail value:
    the redirect target for ``moved``, the failure reason otherwise, ``None``
    for ``ok`` (and for skipped probes, where ``status`` is also ``None``).

    ``detail`` is hard-capped to the column width — see HEALTH_DETAIL_MAXLEN."""
    if detail is not None and len(detail) > HEALTH_DETAIL_MAXLEN:
        detail = detail[: HEALTH_DETAIL_MAXLEN - 1] + "…"
    return {"code": code, "status": status, "detail": detail}


async def probe(client: httpx.AsyncClient, code: str, url: str | None) -> dict:
    """Probe one source into a {code, status, detail} verdict.

    Redirects are followed by hand (``follow_redirects=False``) so every hop's
    host can be vetted with :func:`host_is_public` before a request is sent —
    this is what stops a redirect chain from reaching internal services."""
    if not url or url == "None":
        # No URL to probe — leave it as-is rather than inventing a verdict.
        return _verdict(code, None, "no base_url")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        # A malformed base_url is a config error, not a reachability verdict.
        return _verdict(code, None, f"bad base_url: {url[:80]}")

    current = url
    try:
        for _ in range(MAX_REDIRECTS + 1):
            host = urlsplit(current).hostname
            if not host_is_public(host):
                # Host does not resolve, or resolves to a non-public address —
                # refuse to probe it. From an editor's view the source is
                # effectively unreachable.
                return _verdict(code, "unreachable", f"unresolvable or non-public host: {host}")
            resp = await client.get(current, follow_redirects=False, timeout=TIMEOUT)
            if resp.is_redirect and "location" in resp.headers:
                current = str(httpx.URL(current).join(resp.headers["location"]))
                continue
            status = classify_health(
                error=None,
                status_code=resp.status_code,
                requested_url=url,
                final_url=current,
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
            return _verdict(code, status, detail)

        # Redirect budget exhausted.
        status = classify_health(
            error="redirect_loop", status_code=None, requested_url=url, final_url=None
        )
        return _verdict(code, status, f"exceeded {MAX_REDIRECTS} redirect hops")
    except Exception as exc:  # every probe failure maps to a health verdict
        kind = _error_kind(exc)
        status = classify_health(error=kind, status_code=None, requested_url=url, final_url=None)
        return _verdict(code, status, f"{kind}: {str(exc)[:160]}")


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
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, verify=True) as client:

        async def bounded(code: str, url: str | None) -> dict:
            async with semaphore:
                return await probe(client, code, url)

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
                        "    health_detail = :d, unreachable_since = :u "
                        "WHERE code = :c AND is_active = true"
                    ),
                    {
                        "s": r["status"],
                        "t": checked_at,
                        "d": r["detail"],
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
