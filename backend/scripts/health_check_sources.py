"""Probe every active data source and persist its health_status.

巡检所有活跃数据源的可达性，将结果写入 data_sources.health_status /
health_checked_at，并失效 sources 列表缓存。

Designed to run from cron (see docs/deployment / VPS crontab). Independent of
``is_active``: a source can be reachable-but-deprecated, or down-but-kept.

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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.api.sources import SOURCES_LIST_CACHE_KEY
from app.config import settings
from app.services.source_health import SSL_ERROR, classify_health

TIMEOUT = 15  # seconds per request
CONCURRENCY = 10  # max concurrent probes — be gentle on small academic sites
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


async def probe(client: httpx.AsyncClient, code: str, url: str | None) -> dict:
    """Probe one source and return {code, status} where status is a health_status."""
    if not url or url == "None":
        # No URL to probe — leave it as-is rather than inventing a verdict.
        return {"code": code, "status": None, "detail": "no base_url"}
    try:
        resp = await client.get(url, follow_redirects=True, timeout=TIMEOUT)
        status = classify_health(
            error=None,
            status_code=resp.status_code,
            requested_url=url,
            final_url=str(resp.url),
        )
        detail = f"HTTP {resp.status_code}"
        if str(resp.url) != url:
            detail += f" -> {resp.url}"
        return {"code": code, "status": status, "detail": detail}
    except Exception as exc:  # every probe failure maps to a health verdict
        kind = _error_kind(exc)
        status = classify_health(error=kind, status_code=None, requested_url=url, final_url=None)
        return {"code": code, "status": status, "detail": f"{kind}: {str(exc)[:120]}"}


async def main(dry_run: bool) -> None:
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT code, base_url FROM data_sources "
                    "WHERE is_active = true ORDER BY code"
                )
            )
        ).fetchall()

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

    # ---- write back ----
    changed = 0
    if not dry_run:
        async with async_session() as session:
            for r in verdicts:
                res = await session.execute(
                    text(
                        "UPDATE data_sources "
                        "SET health_status = :s, health_checked_at = now() "
                        "WHERE code = :c AND is_active = true"
                    ),
                    {"s": r["status"], "c": r["code"]},
                )
                changed += res.rowcount or 0
            await session.commit()

    await engine.dispose()

    # ---- bust the sources list cache so the UI badge reflects new verdicts ----
    if not dry_run and verdicts:
        try:
            redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
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
            print(f"  {r['code']:36s} {r['detail']}")
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
