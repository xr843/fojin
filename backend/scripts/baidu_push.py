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
reachable). The token is read from stdin so it never sits in the environment,
the process list, or a compose file:

    python scripts/baidu_push.py --dry-run --token-stdin < token-file
    python scripts/baidu_push.py --kind all --limit 50 --token-stdin \
        --state-file /data/baidu-push/state.json < token-file

``--state-file`` makes each run continue where the previous one stopped; without
it every run re-pushes the same leading slice. BAIDU_PUSH_TOKEN still works as a
fallback when --token-stdin is not given.
"""

import argparse
import asyncio
import json
import os
import re
import socket
import ssl
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

PUSH_API_HOST = "data.zz.baidu.com"
PUSH_API_URL = f"https://{PUSH_API_HOST}/urls"
DEFAULT_LIMIT = 10  # fojin.app's daily quota on 2026-10-19 (Baidu's remain field)

# Baidu's own docs give the endpoint as plain http://, which would put the token
# on the wire in clear text. https works, but the certificate is issued for
# ``*.baidu.com`` — a wildcard only covers one label, so ``data.zz.baidu.com``
# fails strict hostname matching (checked 2026-10-19). We therefore keep full
# chain verification against the system CAs, turn off *only* the hostname match,
# and pin the identity ourselves before any token is sent: the leaf must be
# issued to Baidu's operating company and carry the ``*.baidu.com`` SAN.
_EXPECTED_ORG = "Beijing Baidu Netcom Science Technology Co., Ltd."
_EXPECTED_SAN = "*.baidu.com"


def _baidu_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


def _check_baidu_cert(cert: dict) -> None:
    """Raise ssl.SSLError unless the (already chain-verified) leaf is Baidu's."""
    orgs = {v for rdn in cert.get("subject", ()) for k, v in rdn if k == "organizationName"}
    sans = {v for k, v in cert.get("subjectAltName", ()) if k == "DNS"}
    if _EXPECTED_ORG not in orgs or _EXPECTED_SAN not in sans:
        raise ssl.SSLError(f"unexpected certificate for {PUSH_API_HOST}: org={sorted(orgs)}")


def verify_push_endpoint(timeout: float = 15) -> None:
    """Handshake with the push host and pin its certificate identity.

    Runs before the token is sent. A chain that doesn't verify raises during the
    handshake (CERT_REQUIRED); a verified chain for someone else raises here.
    """
    with (
        socket.create_connection((PUSH_API_HOST, 443), timeout=timeout) as raw,
        _baidu_ssl_context().wrap_socket(raw, server_hostname=PUSH_API_HOST) as tls,
    ):
        _check_baidu_cert(tls.getpeercert())


def _redact(text: str, token: str) -> str:
    """httpx errors quote the full request URL, token query param included —
    never let that reach stdout/stderr (cron logs)."""
    text = re.sub(r"(token=)[^&\s'\"]+", r"\1***", text)
    # Also the bare value wherever it appears — but only a realistic one: Baidu
    # tokens are 16 chars, and masking a 3-char test value would eat words.
    return text.replace(token, "***") if token and len(token) >= 8 else text


async def _text_urls(session: AsyncSession, limit: int, offset: int = 0) -> list[str]:
    """Text reader pages, mirroring app.api.sitemap.sitemap_texts."""
    if limit <= 0:
        return []
    texts = await get_all_text_ids_with_dates(session)
    return [f"{BASE_URL}/texts/{text_id}" for text_id, _ in texts[offset : offset + limit]]


async def _person_urls(session: AsyncSession, limit: int, offset: int = 0) -> list[str]:
    """KG person pages, mirroring app.api.sitemap.sitemap_persons."""
    if limit <= 0:
        return []
    result = await session.execute(
        select(KGEntity.id)
        .where(KGEntity.entity_type == "person")
        .order_by(KGEntity.id.asc())
        .offset(offset)
        .limit(limit)
    )
    return [f"{BASE_URL}/persons/{pid}" for (pid,) in result.all()]


async def _dict_urls(session: AsyncSession, limit: int, offset: int = 0) -> list[str]:
    """Dictionary headword pages, mirroring app.api.sitemap.sitemap_dict —
    including its junk-headword filter, so we never push a URL the sitemap
    itself would skip."""
    if limit <= 0:
        return []
    rows = await get_distinct_headwords(session, offset=offset, limit=limit)
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

    NOTE: this always samples the *same* leading slice of each table (offset
    0). Scheduled runs should use --state-file (collect_with_cursor), which
    resumes where the last accepted push stopped.
    """
    kinds = _COLLECTORS.keys() if kind == "all" else (kind,)
    urls: list[str] = []
    for k in kinds:
        remaining = limit - len(urls)
        if remaining <= 0:
            break
        urls.extend(await _COLLECTORS[k](session, remaining))
    return urls


def load_state(path: str | None) -> dict[str, int]:
    if not path or not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return {k: int(v) for k, v in data.get("offsets", {}).items() if k in _COLLECTORS}


def save_state(path: str, offsets: dict[str, int]) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"offsets": offsets}, fh)
    os.replace(tmp, path)


async def collect_with_cursor(
    session: AsyncSession, kind: str, limit: int, offsets: dict[str, int]
) -> tuple[list[str], dict[str, int]]:
    """Like collect_urls, but resumes each kind where the last run stopped.

    A daily cron that always pushes the same leading slice never reaches the
    rest of the catalogue (10k texts, 500k+ headwords). Each kind keeps its own
    offset; a kind that returns fewer rows than asked is exhausted and the budget
    moves on to the next. When every requested kind is exhausted, offsets wrap to
    0 — re-pushing is harmless, and a dead cron would be worse.

    Offsets are returned, not saved: the caller persists them only after Baidu
    accepted the batch, so a failed push is retried next run.
    """
    kinds = list(_COLLECTORS.keys()) if kind == "all" else [kind]
    new = dict(offsets)
    urls: list[str] = []
    for wrapped in (False, True):
        for k in kinds:
            remaining = limit - len(urls)
            if remaining <= 0:
                return urls, new
            start = new.get(k, 0)
            got = await _COLLECTORS[k](session, remaining, offset=start)
            urls.extend(got)
            new[k] = start + len(got)
        if urls or wrapped:
            return urls, new
        new = {k: 0 for k in new}
    return urls, new


async def push_urls(urls: list[str], token: str) -> dict:
    """POST urls to Baidu's active-push endpoint; return the parsed JSON body.

    The query string is built by hand: Baidu rejects a percent-encoded ``site``
    (``site=https%3A%2F%2Ffojin.app`` → 400, while ``site=https://fojin.app`` is
    accepted — both measured on 2026-10-19), and httpx's ``params=`` encodes it.

    Baidu answers quota/site/token problems with a 4xx *and* a JSON body such as
    ``{"error": 400, "message": "over quota"}``; that body is returned so main()
    can print the reason. Raises httpx.HTTPError for transport failures and for
    error responses without a JSON body.
    """
    async with httpx.AsyncClient(timeout=30, verify=_baidu_ssl_context()) as client:
        resp = await client.post(
            f"{PUSH_API_URL}?site={BASE_URL}&token={token}",
            content="\n".join(urls),
            headers={"Content-Type": "text/plain"},
        )
    if resp.is_client_error:
        try:
            body = resp.json()
        except ValueError:
            body = None
        if isinstance(body, dict) and "error" in body:
            return body
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
        "--token-stdin",
        action="store_true",
        help="read the token from the first line of stdin instead of BAIDU_PUSH_TOKEN "
        "(keeps it out of the environment and the process list)",
    )
    parser.add_argument(
        "--state-file",
        help="JSON file holding per-kind offsets; each run continues where the last one stopped",
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
    token = sys.stdin.readline().strip() if args.token_stdin else settings.baidu_push_token
    if not token:
        print(
            "ERROR: BAIDU_PUSH_TOKEN is not set. Get one from "
            "百度搜索资源平台 (ziyuan.baidu.com) → 站点管理 → 普通收录 → API 提交, "
            "then export it as BAIDU_PUSH_TOKEN (see .env.example).",
            file=sys.stderr,
        )
        return 1

    offsets = load_state(args.state_file)
    async with async_session() as session:
        if args.state_file:
            urls, new_offsets = await collect_with_cursor(session, args.kind, args.limit, offsets)
        else:
            urls, new_offsets = await collect_urls(session, args.kind, args.limit), None

    if not urls:
        print("No URLs to push (empty result set).")
        return 0

    if args.dry_run:
        print(f"[dry-run] would push {len(urls)} URL(s):")
        for url in urls:
            print(url)
        return 0

    try:
        await asyncio.to_thread(verify_push_endpoint)
    except (OSError, ssl.SSLError) as exc:
        print(f"ERROR: refusing to send the token, endpoint check failed: {exc}", file=sys.stderr)
        return 1

    try:
        result = await push_urls(urls, token)
    except httpx.HTTPError as exc:
        print(f"ERROR: Baidu push request failed: {_redact(str(exc), token)}", file=sys.stderr)
        return 1

    if "error" in result:
        print(f"ERROR: Baidu push API rejected the request: {_redact(str(result), token)}", file=sys.stderr)
        return 1

    if args.state_file and new_offsets is not None:
        save_state(args.state_file, new_offsets)

    print(f"pushed={len(urls)} success={result.get('success')} remain={result.get('remain')}")
    if result.get("not_same_site"):
        print(f"not_same_site: {result['not_same_site']}")
    if result.get("not_valid"):
        print(f"not_valid: {result['not_valid']}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
