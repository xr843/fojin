"""Push FoJin page URLs to Baidu's "主动推送(实时)" active-push API.

Background (2026-08, measured against prod access logs): ~70% of fojin.app's
traffic is from mainland China, but real Baiduspider crawls over the prior 30
days = 0 (the only 8 hits on record were a manually spoofed UA used to
confirm this). Bingbot crawled 3,925 times / Googlebot 287 times in the same
window. ``frontend/public/baidu_verify_codeva-D2dL1m9tvp.html`` shows the
site *was* registered with 百度搜索资源平台 at some point, but nothing has
been submitted since — Baidu has never actually been told these URLs exist.

This script POSTs URLs (plain text, one per line) to Baidu's active-push
endpoint so it can discover pages without waiting for an organic crawl:

    POST http://data.zz.baidu.com/urls?site={site}&token={token}

IMPORTANT — what this does NOT solve: active push only tells Baidu a URL
exists; it does not guarantee a crawl or an index entry. If Baidu is
throttling/deprioritizing this site for being hosted outside mainland China
without an ICP filing (a live hypothesis, not confirmed either way), pushing
URLs faster will not fix that — the 0-crawl number could just as easily be
policy as discovery. Treat this as a cheap, safe experiment, not a fix.

URL source: this mirrors the same page shapes ``app.api.sitemap`` serves
(texts, dict headwords, persons), built directly off the DB/service layer
rather than by making an HTTP round-trip to the running sitemap endpoints —
more robust to run standalone / from cron without assuming the app server is
up on a known port.

Quota: Baidu's active-push quota is per-site, starts small for a new/
low-volume site and grows over time; the API response's ``remain`` field is
the authoritative count for what's left today. ``--limit`` defaults
conservatively — raise it once ``remain`` shows real headroom.

Usage (inside the backend container, or locally with backend deps + DB
reachable):

    BAIDU_PUSH_TOKEN=xxx python scripts/baidu_push.py --dry-run
    BAIDU_PUSH_TOKEN=xxx python scripts/baidu_push.py --kind texts --limit 50
    BAIDU_PUSH_TOKEN=xxx python scripts/baidu_push.py --kind all --limit 100
"""

import argparse
import asyncio
import os
import sys
from collections.abc import Awaitable, Callable
from urllib.parse import quote

# Allow `python scripts/baidu_push.py` to find the `app` package regardless
# of invocation cwd — same fix as scripts/audit_sources.py and
# scripts/backfill_mitra_scores.py (running a script directly puts the
# script's own directory, not backend/, on sys.path).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.seo_dict import get_distinct_headwords
from app.api.sitemap import BASE_URL
from app.config import settings
from app.database import async_session
from app.models.knowledge_graph import KGEntity
from app.services.text import get_all_text_ids_with_dates

PUSH_API_URL = "http://data.zz.baidu.com/urls"
DEFAULT_LIMIT = 100


async def _text_urls(session: AsyncSession, limit: int) -> list[str]:
    """Text reader pages, mirroring app.api.sitemap.sitemap_texts."""
    if limit <= 0:
        return []
    texts = await get_all_text_ids_with_dates(session)
    return [f"{BASE_URL}/texts/{text_id}" for text_id, _ in texts[:limit]]


async def _person_urls(session: AsyncSession, limit: int) -> list[str]:
    """KG person pages, mirroring app.api.sitemap.sitemap_persons."""
    if limit <= 0:
        return []
    result = await session.execute(
        select(KGEntity.id).where(KGEntity.entity_type == "person").order_by(KGEntity.id.asc()).limit(limit)
    )
    return [f"{BASE_URL}/persons/{pid}" for (pid,) in result.all()]


async def _dict_urls(session: AsyncSession, limit: int) -> list[str]:
    """Dictionary headword pages, mirroring app.api.sitemap.sitemap_dict —
    including its junk-headword filter, so we never push a URL the sitemap
    itself would skip."""
    if limit <= 0:
        return []
    rows = await get_distinct_headwords(session, offset=0, limit=limit)
    urls = []
    for headword, _ in rows:
        if not headword or len(headword) > 200 or "\n" in headword or "\t" in headword:
            continue
        urls.append(f"{BASE_URL}/dict/{quote(headword, safe='')}")
    return urls


# Order matters for --kind all: texts and persons are small tables fetched
# in one query; dict is 500k+ rows queried with an explicit LIMIT, so it
# goes last and is skipped entirely once texts+persons already filled the
# budget (see collect_urls).
_COLLECTORS: dict[str, Callable[[AsyncSession, int], Awaitable[list[str]]]] = {
    "texts": _text_urls,
    "persons": _person_urls,
    "dict": _dict_urls,
}


async def collect_urls(session: AsyncSession, kind: str, limit: int) -> list[str]:
    """Collect up to `limit` page URLs for `kind` ("texts"|"persons"|"dict"|"all").

    For "all", each collector is asked for only as many URLs as remain in the
    budget, in the order above — so a small --limit never pulls more than it
    needs from the largest table (dict), and dict is skipped entirely once
    texts+persons already fill the quota.

    NOTE: this always samples the *same* leading slice of each table (id /
    alphabetical order, offset 0) — there's no persisted cursor, so repeated
    runs re-push the same first N URLs rather than rotating through the full
    catalog. Fine for today's small, conservative --limit; would need a
    stored offset to eventually reach full-catalog coverage.
    """
    kinds = _COLLECTORS.keys() if kind == "all" else (kind,)
    urls: list[str] = []
    for k in kinds:
        remaining = limit - len(urls)
        if remaining <= 0:
            break
        urls.extend(await _COLLECTORS[k](session, remaining))
    return urls


async def push_urls(urls: list[str], token: str) -> dict:
    """POST urls to Baidu's active-push endpoint; return the parsed JSON body.

    Raises httpx.HTTPError (connection/timeout/4xx/5xx) on transport or HTTP
    failure — callers decide how to report that.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            PUSH_API_URL,
            params={"site": BASE_URL, "token": token},
            content="\n".join(urls),
            headers={"Content-Type": "text/plain"},
        )
    resp.raise_for_status()
    return resp.json()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Push FoJin URLs to Baidu's active-push (主动推送) API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--kind",
        choices=[*_COLLECTORS.keys(), "all"],
        default="all",
        help="which page type to push (default: all)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"max URLs to push this run (default: {DEFAULT_LIMIT} — Baidu's daily quota starts small)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the URLs that would be pushed; make no network request",
    )
    return parser


async def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.limit < 1:
        print("ERROR: --limit must be >= 1", file=sys.stderr)
        return 1

    # Checked first and unconditionally — dry-run included. A cron job that
    # silently no-ops because the token was never configured is exactly the
    # failure mode to avoid, and --dry-run should rehearse the real run's
    # config, not just its URL collection.
    token = settings.baidu_push_token
    if not token:
        print(
            "ERROR: BAIDU_PUSH_TOKEN is not set. Get one from "
            "百度搜索资源平台 (ziyuan.baidu.com) → 站点管理 → 普通收录 → API 提交, "
            "then export it as BAIDU_PUSH_TOKEN (see .env.example).",
            file=sys.stderr,
        )
        return 1

    async with async_session() as session:
        urls = await collect_urls(session, args.kind, args.limit)

    if not urls:
        print("No URLs to push (empty result set).")
        return 0

    if args.dry_run:
        print(f"[dry-run] would push {len(urls)} URL(s):")
        for url in urls:
            print(url)
        return 0

    try:
        result = await push_urls(urls, token)
    except httpx.HTTPError as exc:
        print(f"ERROR: Baidu push request failed: {exc}", file=sys.stderr)
        return 1

    if "error" in result:
        print(f"ERROR: Baidu push API rejected the request: {result}", file=sys.stderr)
        return 1

    print(f"pushed={len(urls)} success={result.get('success')} remain={result.get('remain')}")
    if result.get("not_same_site"):
        print(f"not_same_site: {result['not_same_site']}")
    if result.get("not_valid"):
        print(f"not_valid: {result['not_valid']}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
