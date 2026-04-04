#!/usr/bin/env python3
"""Fetch academic and Buddhist news feeds into the academic_feeds table.

Usage:
    cd backend
    python scripts/fetch_academic_feeds.py [--source NAME] [--stats]
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import xml.etree.ElementTree as _stdlib_ET

import httpx
from defusedxml import ElementTree as ET

# defusedxml provides safe parse/fromstring but ParseError lives in stdlib
ParseError = _stdlib_ET.ParseError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.feed import AcademicFeed

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feed registry
# ---------------------------------------------------------------------------

FEED_REGISTRY: list[dict] = [
    {
        "name": "84000_blog",
        "url": "https://84000.co/feed/",
        "category": "translation",
        "language": "en",
    },
    {
        "name": "bdrc_news",
        "url": "https://www.bdrc.io/feed/",
        "category": "digitization",
        "language": "en",
    },
    {
        "name": "bdk_america",
        "url": "https://www.bdkamerica.org/feed/",
        "category": "translation",
        "language": "en",
    },
    {
        "name": "buddhistdoor",
        "url": "https://www.buddhistdoor.net/feed/",
        "category": "news",
        "language": "en",
    },
    {
        "name": "lions_roar",
        "url": "https://www.lionsroar.com/feed/",
        "category": "news",
        "language": "en",
    },
    {
        "name": "tricycle",
        "url": "https://tricycle.org/feed/",
        "category": "news",
        "language": "en",
    },
    {
        "name": "accesstoinsight",
        "url": "https://www.accesstoinsight.org/rss.xml",
        "category": "translation",
        "language": "en",
    },
    {
        "name": "iabs",
        "url": "https://journals.ub.uni-heidelberg.de/index.php/jiabs/gateway/plugin/WebFeedGatewayPlugin/atom",
        "category": "paper",
        "language": "en",
    },
]

# XML namespace map for Atom feeds
ATOM_NS = "http://www.w3.org/2005/Atom"
DC_NS = "http://purl.org/dc/elements/1.1/"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"

USER_AGENT = "FoJin Academic Feed Fetcher/1.0"
FEED_TIMEOUT = 30  # seconds per feed


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_rss_date(date_str: str | None) -> datetime | None:
    """Parse an RFC 2822 date (common in RSS 2.0)."""
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str.strip())
    except Exception:
        return _parse_iso_date(date_str)


def _parse_iso_date(date_str: str | None) -> datetime | None:
    """Parse an ISO 8601 / Atom date string."""
    if not date_str:
        return None
    date_str = date_str.strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _clean_text(text_val: str | None, max_len: int = 0) -> str | None:
    """Strip whitespace; optionally truncate."""
    if text_val is None:
        return None
    cleaned = text_val.strip()
    if not cleaned:
        return None
    if max_len and len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 1] + "\u2026"
    return cleaned


def _strip_html(raw: str | None) -> str | None:
    """Crude HTML tag stripping for summary text."""
    if raw is None:
        return None
    import re
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"\s+", " ", text).strip()
    return text if text else None


def _parse_rss_items(root: _stdlib_ET.Element, feed_config: dict) -> list[dict]:  # type: ignore[name-defined]
    """Parse RSS 2.0 <item> elements."""
    entries = []
    for item in root.iter("item"):
        title = _clean_text(item.findtext("title"), max_len=500)
        link = _clean_text(item.findtext("link"))
        if not title or not link:
            continue

        # Summary: prefer <description>, strip HTML
        raw_summary = item.findtext("description") or item.findtext(
            f"{{{CONTENT_NS}}}encoded"
        )
        summary = _clean_text(_strip_html(raw_summary), max_len=2000)

        author = _clean_text(
            item.findtext(f"{{{DC_NS}}}creator") or item.findtext("author"),
            max_len=200,
        )
        published_at = _parse_rss_date(item.findtext("pubDate"))

        entries.append(
            {
                "feed_source": feed_config["name"],
                "title": title,
                "url": link,
                "summary": summary,
                "author": author,
                "category": feed_config["category"],
                "language": feed_config["language"],
                "published_at": published_at,
            }
        )
    return entries


def _parse_atom_entries(root: _stdlib_ET.Element, feed_config: dict) -> list[dict]:  # type: ignore[name-defined]
    """Parse Atom <entry> elements."""
    entries = []
    for entry in root.iter(f"{{{ATOM_NS}}}entry"):
        title_el = entry.find(f"{{{ATOM_NS}}}title")
        title = _clean_text(title_el.text if title_el is not None else None, max_len=500)

        # Atom links: prefer rel="alternate", fall back to first <link>
        link = None
        for link_el in entry.findall(f"{{{ATOM_NS}}}link"):
            href = link_el.get("href")
            rel = link_el.get("rel", "alternate")
            if rel == "alternate" and href:
                link = href.strip()
                break
            if href and link is None:
                link = href.strip()

        if not title or not link:
            continue

        # Summary
        summary_el = entry.find(f"{{{ATOM_NS}}}summary")
        content_el = entry.find(f"{{{ATOM_NS}}}content")
        raw_summary = None
        if summary_el is not None and summary_el.text:
            raw_summary = summary_el.text
        elif content_el is not None and content_el.text:
            raw_summary = content_el.text
        summary = _clean_text(_strip_html(raw_summary), max_len=2000)

        # Author
        author_el = entry.find(f"{{{ATOM_NS}}}author")
        author = None
        if author_el is not None:
            name_el = author_el.find(f"{{{ATOM_NS}}}name")
            if name_el is not None:
                author = _clean_text(name_el.text, max_len=200)

        # Date
        published_str = None
        for tag in (f"{{{ATOM_NS}}}published", f"{{{ATOM_NS}}}updated"):
            el = entry.find(tag)
            if el is not None and el.text:
                published_str = el.text
                break
        published_at = _parse_iso_date(published_str)

        entries.append(
            {
                "feed_source": feed_config["name"],
                "title": title,
                "url": link,
                "summary": summary,
                "author": author,
                "category": feed_config["category"],
                "language": feed_config["language"],
                "published_at": published_at,
            }
        )
    return entries


# ---------------------------------------------------------------------------
# Core async functions
# ---------------------------------------------------------------------------


async def fetch_and_parse_feed(
    client: httpx.AsyncClient, feed_config: dict
) -> list[dict]:
    """Fetch a single RSS/Atom feed and return parsed entries."""
    url = feed_config["url"]
    name = feed_config["name"]

    try:
        resp = await client.get(url, follow_redirects=True, timeout=FEED_TIMEOUT)
        resp.raise_for_status()
    except httpx.TimeoutException:
        logger.warning("[%s] Timeout fetching %s", name, url)
        return []
    except httpx.HTTPStatusError as exc:
        logger.warning("[%s] HTTP %d from %s", name, exc.response.status_code, url)
        return []
    except httpx.HTTPError as exc:
        logger.warning("[%s] Network error fetching %s: %s", name, url, exc)
        return []

    try:
        root = ET.fromstring(resp.content)
    except ParseError as exc:
        logger.warning("[%s] XML parse error: %s", name, exc)
        return []

    # Detect feed format
    tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag

    if tag == "feed":
        # Atom
        entries = _parse_atom_entries(root, feed_config)
    elif tag == "rss" or tag == "RDF" or root.find("channel") is not None:
        # RSS 2.0 (or RSS 1.0 / RDF)
        entries = _parse_rss_items(root, feed_config)
    else:
        logger.warning("[%s] Unknown feed format: root tag = %s", name, root.tag)
        return []

    logger.info("[%s] Parsed %d entries from %s", name, len(entries), url)
    return entries


async def upsert_entries(
    session_factory: async_sessionmaker, entries: list[dict], feed_source: str
) -> tuple[int, int]:
    """Insert new entries, skip duplicates (matched by url).

    Returns (inserted_count, skipped_count).
    """
    inserted = 0
    skipped = 0

    async with session_factory() as session:
        # Batch check existing URLs to avoid N+1 queries
        urls = [e["url"] for e in entries]
        result = await session.execute(
            select(AcademicFeed.url).where(AcademicFeed.url.in_(urls))
        )
        existing_urls = set(result.scalars().all())

        for entry in entries:
            if entry["url"] in existing_urls:
                skipped += 1
                continue

            record = AcademicFeed(**entry)
            session.add(record)
            inserted += 1

        if inserted > 0:
            await session.commit()

    return inserted, skipped


async def show_stats(session_factory: async_sessionmaker) -> None:
    """Print per-source entry counts."""
    async with session_factory() as session:
        result = await session.execute(
            text(
                "SELECT feed_source, COUNT(*), MAX(published_at), MAX(fetched_at) "
                "FROM academic_feeds GROUP BY feed_source ORDER BY feed_source"
            )
        )
        rows = result.fetchall()

    if not rows:
        print("No entries in academic_feeds table.")
        return

    print(f"\n{'Source':<25s} {'Count':>6s}  {'Latest Published':<25s} {'Latest Fetched':<25s}")
    print("-" * 85)
    total = 0
    for source, count, latest_pub, latest_fetch in rows:
        total += count
        pub_str = str(latest_pub)[:19] if latest_pub else "-"
        fetch_str = str(latest_fetch)[:19] if latest_fetch else "-"
        print(f"{source:<25s} {count:>6d}  {pub_str:<25s} {fetch_str:<25s}")
    print("-" * 85)
    print(f"{'TOTAL':<25s} {total:>6d}")
    print()


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch academic/Buddhist feeds into academic_feeds table."
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Only fetch a specific feed source (e.g. 84000_blog)",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show per-source entry counts and exit",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        if args.stats:
            await show_stats(session_factory)
            return

        # Determine which feeds to process
        feeds = FEED_REGISTRY
        if args.source:
            feeds = [f for f in FEED_REGISTRY if f["name"] == args.source]
            if not feeds:
                valid = ", ".join(f["name"] for f in FEED_REGISTRY)
                logger.error("Unknown source %r. Valid sources: %s", args.source, valid)
                sys.exit(1)

        total_inserted = 0
        total_skipped = 0

        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            for feed_config in feeds:
                name = feed_config["name"]
                entries = await fetch_and_parse_feed(client, feed_config)

                if not entries:
                    logger.info("[%s] No entries to insert.", name)
                    continue

                inserted, skipped = await upsert_entries(
                    session_factory, entries, name
                )
                total_inserted += inserted
                total_skipped += skipped
                logger.info(
                    "[%s] Inserted %d, skipped %d duplicates.",
                    name, inserted, skipped,
                )

        print(
            f"\nDone. {total_inserted} new entries inserted, "
            f"{total_skipped} duplicates skipped across {len(feeds)} feed(s)."
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
