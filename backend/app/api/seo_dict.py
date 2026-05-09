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
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api.seo import _escape_meta_value
from app.database import get_db
from app.models.dictionary import DictionaryEntry
from app.models.text import BuddhistText, TextContent

logger = logging.getLogger(__name__)
router = APIRouter(tags=["seo"])

_DEFINITION_PREVIEW_CHARS = 220
_REVERSE_INDEX_LIMIT = 8
_MAX_HEADWORD_LEN = 200


def _build_dict_jsonld(headword: str, entries: list[DictionaryEntry], canonical: str) -> dict:
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

    Uses a vanilla ILIKE — text_contents.content is GiST-trigram-indexed so
    a single-term substring match is sub-second for the largest sutras.
    """
    if len(headword) > _MAX_HEADWORD_LEN:
        return []
    stmt = (
        select(BuddhistText.id, BuddhistText.title_zh, BuddhistText.cbeta_id)
        .join(TextContent, TextContent.text_id == BuddhistText.id)
        .where(TextContent.content.ilike(f"%{headword}%"))
        .group_by(BuddhistText.id, BuddhistText.title_zh, BuddhistText.cbeta_id)
        .order_by(BuddhistText.id.asc())
        .limit(_REVERSE_INDEX_LIMIT)
    )
    rows = await db.execute(stmt)
    return [
        {"id": r[0], "title_zh": (r[1] or "").strip(), "cbeta_id": (r[2] or "").strip()}
        for r in rows.all()
    ]


def _render_dict_html(
    headword: str,
    entries: list[DictionaryEntry],
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
    by_source: dict[str, list[DictionaryEntry]] = {}
    for e in entries:
        key = e.source.name_zh if e.source else "其他"
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

    stmt = (
        select(DictionaryEntry)
        .options(joinedload(DictionaryEntry.source))
        .where(DictionaryEntry.headword == headword)
        .limit(50)
    )
    rows = await db.execute(stmt)
    entries = list(rows.unique().scalars().all())
    if not entries:
        raise HTTPException(status_code=404, detail="headword not found")

    base_url = str(request.base_url).rstrip("/")
    canonical = f"{base_url}/dict/{headword}"

    try:
        related = await _fetch_reverse_index(db, headword)
    except Exception as e:  # reverse index is best-effort
        logger.warning("dict reverse index failed for %s: %s", headword, e)
        related = []

    html = _render_dict_html(
        headword,
        entries,
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
