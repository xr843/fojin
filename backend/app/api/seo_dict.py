"""Server-rendered SEO landing pages for Buddhist dictionary headwords.

747k+ dictionary entries across multiple sources (DDB / Soothill / FGS / etc)
were previously exposed only via the SPA ``/dictionary`` modal. Search engines
saw nothing — yet "苦谛 是什么意思" / "般若 解释" type queries are exactly the
kind of long-tail traffic Google rewards heavily for niche knowledge sites.

This module renders a standalone HTML page per *headword* (not per entry, since
the same word can appear across multiple dictionaries). Crawlers + external
citations land here; users still hit the SPA ``/dictionary`` from in-app links.

URL shape: ``/dict/{headword}``
- ``headword`` is the literal Chinese / Sanskrit / Pali term, URL-encoded by
  the client. Google indexes UTF-8 URLs fine and they show up in SERP slugs.
- Aggregates every ``DictionaryEntry`` row matching that headword across all
  sources; renders one section per source.

Reverse-index "this term appears in N sutras" comes from a substring match
against ``text_contents.content`` capped at the first 5 hits — cheap,
correct enough for the seed iteration.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from opencc import OpenCC
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api.seo import _escape_meta_value
from app.database import get_db
from app.models.dictionary import DictionaryEntry
from app.models.text import BuddhistText, TextContent

# Dictionary entries are stored in traditional Chinese (CBETA / DDB / FGS
# convention). Users typing simplified Chinese in the URL must be matched
# against the traditional form; dictionary.py uses the same pattern.
_s2t = OpenCC("s2t")
_t2s = OpenCC("t2s")

logger = logging.getLogger(__name__)
router = APIRouter(tags=["seo"])

_DEFINITION_PREVIEW_CHARS = 220
_REVERSE_INDEX_LIMIT = 8
_MAX_HEADWORD_LEN = 200
# pg_trgm can only use ix_text_contents_content_trgm for an unanchored
# ``ILIKE '%term%'`` when the pattern holds at least one *complete* trigram —
# i.e. 3+ characters. At 2 characters the planner extracts nothing and falls
# back to a Seq Scan over 276MB of TOASTed content, so the lookup can never
# finish inside _REVERSE_INDEX_TIMEOUT_MS. This was 2 (single-char only), which
# let every 2-char headword through to a guaranteed-timeout seq scan.
_MIN_HEADWORD_LEN = 3
# Cap how long the best-effort reverse-index lookup may hold a pool connection.
# Terms the trgm index can't serve seq-scan the 406MB content table; bounding
# this (vs the global ~60s) is what stops crawler load from exhausting the pool.
_REVERSE_INDEX_TIMEOUT_MS = 3000


@dataclass(frozen=True, slots=True)
class _DictEntryView:
    """Primitive snapshot of a DictionaryEntry's render-relevant fields.

    The render path runs AFTER the best-effort reverse-index lookup, which may
    time out and roll back the session (see ``_fetch_reverse_index``). A rollback
    expires every joinedload'd ORM row, so touching ``entry.source.name_zh`` /
    ``entry.definition`` during rendering would trigger an async lazy-reload and
    raise MissingGreenlet → 500 (live on /dict/般若 + /dict/菩提, 2026-06-24; the
    #654/#763 detached-row trap, 3rd recurrence). Snapshotting to primitives
    BEFORE the reverse-index call makes rendering immune to any mid-request
    session reset.
    """

    definition: str | None
    reading: str | None
    source_name: str | None


def _build_dict_jsonld(headword: str, entries: list[_DictEntryView], canonical: str) -> dict:
    """schema.org DefinedTerm — Google indexes these as glossary results.

    A headword often has multiple definitions across dictionaries; we fold
    them into ``description`` (joined, truncated) and point ``inDefinedTermSet``
    at the most-trusted source.
    """
    descriptions = []
    for e in entries:
        if e.definition:
            cleaned = e.definition.strip().replace("\n", " ")
            if len(cleaned) > 200:
                cleaned = cleaned[:200] + "…"
            descriptions.append(cleaned)
    main_description = " / ".join(descriptions[:3])[:500] if descriptions else f"佛教术语「{headword}」"

    payload: dict = {
        "@context": "https://schema.org",
        "@type": "DefinedTerm",
        "name": headword,
        "url": canonical,
        "description": main_description,
        "inDefinedTermSet": {
            "@type": "DefinedTermSet",
            "name": "佛津 FoJin 佛学辞典聚合",
            "url": "https://fojin.app/dictionary",
        },
    }
    # Add reading (pronunciation) if any entry has it.
    readings = [e.reading for e in entries if e.reading]
    if readings:
        payload["alternateName"] = list(dict.fromkeys(readings))[:5]
    return payload


async def _fetch_reverse_index(
    db: AsyncSession, headword: str
) -> list[dict]:
    """Return up to N sutras containing this headword in their content.

    text_contents.content has a GIN trigram index (ix_text_contents_content_trgm,
    migration 0157) that serves most ILIKE substring matches sub-second. But
    terms the index can't serve seq-scan the content table for tens of seconds;
    under crawler load those pile up and exhaust the connection pool (prod outage
    2026-06-23). This block is a best-effort SEO nicety, so:
      - skip headwords under _MIN_HEADWORD_LEN chars — pg_trgm cannot extract a
        trigram from them, so they are guaranteed seq scans (see the constant),
      - cap the per-query statement_timeout so a slow lookup fails fast and
        releases its pool connection instead of holding it ~60s; on timeout we
        drop the "appears in N sutras" block rather than starve the pool.
    """
    if not (_MIN_HEADWORD_LEN <= len(headword) <= _MAX_HEADWORD_LEN):
        return []
    stmt = (
        select(BuddhistText.id, BuddhistText.title_zh, BuddhistText.cbeta_id)
        .join(TextContent, TextContent.text_id == BuddhistText.id)
        .where(TextContent.content.ilike(f"%{headword}%"))
        .group_by(BuddhistText.id, BuddhistText.title_zh, BuddhistText.cbeta_id)
        .order_by(BuddhistText.id.asc())
        .limit(_REVERSE_INDEX_LIMIT)
    )
    try:
        # SET LOCAL applies to the request's already-open transaction (the
        # caller fetched entries first), bounding just this lookup.
        await db.execute(text(f"SET LOCAL statement_timeout = '{_REVERSE_INDEX_TIMEOUT_MS}ms'"))
        rows = await db.execute(stmt)
        return [
            {"id": r[0], "title_zh": (r[1] or "").strip(), "cbeta_id": (r[2] or "").strip()}
            for r in rows.all()
        ]
    except SQLAlchemyError as exc:
        # Timeout / cancellation: abort the txn so the session is reusable, drop
        # the block. This is the last DB op of the request, so rollback is safe.
        logger.warning("reverse-index lookup gave up for %r (best-effort): %s", headword, exc)
        await db.rollback()
        return []


def _render_dict_html(
    headword: str,
    entries: list[_DictEntryView],
    related_texts: list[dict],
    *,
    canonical: str,
    base_url: str,
) -> str:
    safe_head = _escape_meta_value(headword)

    # Title + meta description: pull the strongest definition.
    primary_def = ""
    for e in entries:
        if e.definition:
            cleaned = e.definition.strip()
            primary_def = cleaned[:_DEFINITION_PREVIEW_CHARS]
            if len(cleaned) > _DEFINITION_PREVIEW_CHARS:
                primary_def = primary_def + "…"
            break
    if not primary_def:
        primary_def = f"佛教术语「{headword}」释义"

    title = f"{headword} — 佛学辞典释义 | 佛津 FoJin"
    description = f"{headword}：{primary_def} | 佛津 FoJin 聚合 {len(entries)} 部佛学辞典释义。"
    description = description[:300]

    jsonld = json.dumps(
        _build_dict_jsonld(headword, entries, canonical),
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    breadcrumb = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "佛津 FoJin", "item": base_url},
                {"@type": "ListItem", "position": 2, "name": "佛学辞典", "item": f"{base_url}/dictionary"},
                {"@type": "ListItem", "position": 3, "name": headword, "item": canonical},
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")

    css = (
        "body{font-family:-apple-system,Segoe UI,PingFang SC,sans-serif;"
        "max-width:760px;margin:24px auto;padding:0 16px;line-height:1.75;color:#222;}"
        "h1{font-size:2rem;margin:0 0 4px;}"
        "h2{font-size:1.1rem;margin:24px 0 6px;border-bottom:1px solid #ddd;padding-bottom:4px;color:#8b2500;}"
        "h3{font-size:1rem;margin:14px 0 4px;color:#444;}"
        ".reading{color:#888;font-size:1rem;margin:0 0 14px;}"
        ".source{color:#999;font-size:0.85rem;margin:6px 0 0;}"
        ".def{margin:6px 0 14px;color:#333;}"
        ".cta{display:inline-block;margin:12px 12px 12px 0;padding:6px 14px;"
        "background:#8b2500;color:#fff;border-radius:4px;text-decoration:none;}"
        ".cta:hover{background:#6f1d00;}"
        "ul{padding-left:20px;}li{margin:4px 0;}"
        "a{color:#8b2500;text-decoration:none;}a:hover{text-decoration:underline;}"
        "footer{margin-top:32px;color:#888;font-size:0.85rem;border-top:1px solid #eee;padding-top:12px;}"
    )

    parts = [
        "<!doctype html>",
        '<html lang="zh-Hans">',
        "<head>",
        '<meta charset="utf-8" />',
        '<meta name="viewport" content="width=device-width,initial-scale=1" />',
        f"<title>{_escape_meta_value(title)}</title>",
        f'<meta name="description" content="{_escape_meta_value(description)}" />',
        '<meta name="robots" content="index, follow" />',
        f'<link rel="canonical" href="{_escape_meta_value(canonical)}" />',
        '<meta property="og:type" content="article" />',
        f'<meta property="og:title" content="{_escape_meta_value(title)}" />',
        f'<meta property="og:description" content="{_escape_meta_value(description)}" />',
        f'<meta property="og:url" content="{_escape_meta_value(canonical)}" />',
        '<meta property="og:site_name" content="佛津 FoJin" />',
        '<meta name="twitter:card" content="summary" />',
        f"<style>{css}</style>",
        f'<script type="application/ld+json">{jsonld}</script>',
        f'<script type="application/ld+json">{breadcrumb}</script>',
        "</head>",
        "<body>",
        f"<h1>{safe_head}</h1>",
    ]

    readings = [e.reading for e in entries if e.reading]
    readings = list(dict.fromkeys(readings))[:3]
    if readings:
        parts.append('<p class="reading">' + " · ".join(_escape_meta_value(r) for r in readings) + "</p>")

    parts.append(
        f'<div><a class="cta" href="{base_url}/chat?q={safe_head}">用 AI 提问「{safe_head}」</a>'
        f'<a class="cta" href="{base_url}/search?q={safe_head}">在经文中搜索</a></div>'
    )

    # Group entries by source for cleaner layout.
    by_source: dict[str, list[_DictEntryView]] = {}
    for e in entries:
        key = e.source_name or "其他"
        by_source.setdefault(key, []).append(e)

    parts.append(f'<h2>释义（{len(entries)} 部辞典）</h2>')
    for src_name, src_entries in by_source.items():
        parts.append(f"<h3>{_escape_meta_value(src_name)}</h3>")
        for e in src_entries[:3]:  # cap per source to keep page lean
            if e.definition:
                parts.append(f'<p class="def">{_escape_meta_value(e.definition.strip())}</p>')
        if len(src_entries) > 3:
            parts.append(f'<p class="source">…该来源共 {len(src_entries)} 条释义</p>')

    if related_texts:
        parts.append(f'<h2>「{safe_head}」在经文中出现</h2><ul>')
        for t in related_texts:
            t_title = _escape_meta_value(t["title_zh"] or f"佛典 #{t['id']}")
            cbeta = f' (CBETA {_escape_meta_value(t["cbeta_id"])})' if t["cbeta_id"] else ""
            parts.append(
                f'<li><a href="{base_url}/texts/{t["id"]}">《{t_title}》</a>{cbeta}</li>'
            )
        parts.append("</ul>")

    parts.append(
        f'<p><a href="{base_url}/dictionary?q={safe_head}">在词典中查看更多 »</a> · '
        f'<a href="{base_url}/dictionary">浏览全部佛学辞典</a></p>'
    )
    parts.append(
        '<footer>数据来源：佛光大辞典、佛学大辞典、Soothill 佛学英汉词典、CBETA 异体字字典等。'
        '佛津 FoJin 是开源佛教数字人文聚合平台。</footer>'
    )
    parts.append("</body></html>")
    return "".join(parts)


@router.api_route(
    "/dict/{headword:path}",
    methods=["GET", "HEAD"],
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def dict_seo_html(headword: str, request: Request, db: AsyncSession = Depends(get_db)):
    """SSR landing page for a dictionary headword.

    The path parameter is URL-decoded by FastAPI; we cap the length defensively
    and 404 on anything obviously not a term (whitespace-only, too long).
    """
    headword = unquote(headword).strip()
    if not headword or len(headword) > _MAX_HEADWORD_LEN:
        raise HTTPException(status_code=404, detail="invalid headword")

    # Try simplified, traditional, and original variant — dictionary entries
    # are stored in traditional Chinese, but Google / users may arrive with
    # the simplified form. Dedupe to a single SQL roundtrip.
    variants = list({headword, _s2t.convert(headword), _t2s.convert(headword)})
    canonical_headword = headword
    if len(variants) > 1:
        # Probe which variant actually exists; prefer traditional (CBETA convention).
        probe = await db.execute(
            select(DictionaryEntry.headword)
            .where(DictionaryEntry.headword.in_(variants))
            .limit(1)
        )
        found = probe.scalar_one_or_none()
        if found and found != headword:
            # Redirect simplified → canonical traditional URL so we don't
            # split SEO juice across simplified + traditional duplicates.
            return RedirectResponse(url=f"/dict/{found}", status_code=301)
        canonical_headword = found or headword

    stmt = (
        select(DictionaryEntry)
        .options(joinedload(DictionaryEntry.source))
        .where(or_(*[DictionaryEntry.headword == v for v in variants]))
        .limit(50)
    )
    rows = await db.execute(stmt)
    entries = list(rows.unique().scalars().all())
    if not entries:
        raise HTTPException(status_code=404, detail="headword not found")

    # Snapshot to primitives BEFORE the reverse-index lookup: that lookup may
    # roll back the session (timeout guard), which would expire these
    # joinedload'd rows and 500 the render on a lazy-reload. See _DictEntryView.
    views = [
        _DictEntryView(
            definition=e.definition,
            reading=e.reading,
            source_name=(e.source.name_zh if e.source else None),
        )
        for e in entries
    ]

    base_url = str(request.base_url).rstrip("/")
    canonical = f"{base_url}/dict/{canonical_headword}"
    headword = canonical_headword

    try:
        related = await _fetch_reverse_index(db, headword)
    except Exception as e:  # reverse index is best-effort
        logger.warning("dict reverse index failed for %s: %s", headword, e)
        related = []

    html = _render_dict_html(
        headword,
        views,
        related,
        canonical=canonical,
        base_url=base_url,
    )
    return HTMLResponse(content=html, headers={"Cache-Control": "public, max-age=3600"})


# Helper for sitemap: distinct headwords ordered + paged.
async def get_distinct_headwords(
    db: AsyncSession, *, offset: int, limit: int
) -> list[tuple[str, int]]:
    """Return [(headword, entry_count)] paged by alphabet order."""
    stmt = (
        select(DictionaryEntry.headword, func.count(DictionaryEntry.id))
        .group_by(DictionaryEntry.headword)
        .order_by(DictionaryEntry.headword.asc())
        .offset(offset)
        .limit(limit)
    )
    rows = await db.execute(stmt)
    return [(r[0], r[1]) for r in rows.all()]


async def count_distinct_headwords(db: AsyncSession) -> int:
    stmt = select(func.count(func.distinct(DictionaryEntry.headword)))
    return (await db.execute(stmt)).scalar() or 0
