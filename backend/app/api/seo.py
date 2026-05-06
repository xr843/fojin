"""Server-side meta tag injection for SPA routes that need real SEO.

Google's standard crawler does not execute JavaScript, so the React-side
``react-helmet-async`` titles set by ``TextReaderPage`` and friends never
reach the search index. Every text URL ends up advertising the homepage
``<title>`` and ``<meta description>``, which is why GSC reports near-zero
impressions for content queries (sutra names, translator names, CBETA IDs).

This module intercepts a small allowlist of high-value routes — currently
just ``/texts/{id}`` and ``/texts/{id}/read`` — fetches the actual built
``index.html`` from the frontend nginx container, replaces the head meta
tags with text-specific values, and returns the patched HTML. The React
bundle still mounts in the user's browser exactly as before; this only
changes what crawlers (and link-preview bots) see.

The frontend ``index.html`` is cached for 60 seconds so a frontend redeploy
is picked up within a minute without restarting the backend.
"""

import logging
import re
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.chat import SharedQA
from app.services.text import get_text_by_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["seo"])

# Inside the docker compose network, the nginx-served frontend is reachable
# at this hostname. The backend container has no filesystem access to the
# built dist/, so it has to fetch the entry HTML over HTTP.
_FRONTEND_INDEX_URL = "http://frontend/index.html"
_INDEX_HTML_CACHE_TTL = 60.0  # seconds
_index_html_cache: dict[str, object] = {}

_TITLE_RE = re.compile(r"<title>[^<]*</title>", re.IGNORECASE)
_DESCRIPTION_RE = re.compile(
    r'<meta\s+name="description"\s+content="[^"]*"\s*/?>',
    re.IGNORECASE,
)
_CANONICAL_RE = re.compile(
    r'<link\s+rel="canonical"\s+href="[^"]*"\s*/?>',
    re.IGNORECASE,
)
_ROBOTS_RE = re.compile(
    r'<meta\s+name="robots"\s+content="[^"]*"\s*/?>',
    re.IGNORECASE,
)
_HEAD_CLOSE_RE = re.compile(r"</head>", re.IGNORECASE)


def _escape_meta_value(value: str) -> str:
    """Escape characters that would break out of an HTML attribute value."""
    return value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


async def _fetch_index_html() -> str:
    """Fetch the built index.html from the frontend container with TTL caching."""
    now = time.monotonic()
    cached_at = _index_html_cache.get("ts")
    cached_html = _index_html_cache.get("html")
    if isinstance(cached_at, float) and isinstance(cached_html, str) and now - cached_at < _INDEX_HTML_CACHE_TTL:
        return cached_html

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(_FRONTEND_INDEX_URL)
        resp.raise_for_status()
        html = resp.text

    _index_html_cache["html"] = html
    _index_html_cache["ts"] = now
    return html


def _inject_meta(
    html: str,
    title: str,
    description: str,
    canonical_url: str,
    robots: str = "index, follow",
) -> str:
    """Replace <title>, <meta name="description">, <link rel="canonical">, and <meta name="robots">.

    If a canonical link is missing entirely (the default for the React SPA
    template), we add it just before the closing </head> tag.
    """
    safe_title = _escape_meta_value(title)
    safe_desc = _escape_meta_value(description)
    safe_canonical = _escape_meta_value(canonical_url)
    safe_robots = _escape_meta_value(robots)

    new_html = _TITLE_RE.sub(f"<title>{safe_title}</title>", html, count=1)
    new_html = _DESCRIPTION_RE.sub(
        f'<meta name="description" content="{safe_desc}" />',
        new_html,
        count=1,
    )
    new_html = _ROBOTS_RE.sub(
        f'<meta name="robots" content="{safe_robots}" />',
        new_html,
        count=1,
    )
    canonical_tag = f'<link rel="canonical" href="{safe_canonical}" />'
    if _CANONICAL_RE.search(new_html):
        new_html = _CANONICAL_RE.sub(canonical_tag, new_html, count=1)
    else:
        new_html = _HEAD_CLOSE_RE.sub(f"  {canonical_tag}\n  </head>", new_html, count=1)
    return new_html


def _build_text_meta(text, request: Request, *, route: str) -> tuple[str, str, str]:
    """Compose the per-text title, description, and canonical URL.

    ``route`` is either ``"detail"`` (``/texts/{id}``) or ``"read"``
    (``/texts/{id}/read``); the canonical is always self-referencing for the
    requested URL to avoid the bot/browser canonical mismatch that previously
    existed (the prerender Worker pointed ``/texts/{id}`` at itself, while
    this module pointed it at ``/read``).
    """
    title_zh = text.title_zh or "佛典"
    translator = (text.translator or "").strip()
    dynasty = (text.dynasty or "").strip()
    cbeta_id = (text.cbeta_id or "").strip()

    title_parts = [f"《{title_zh}》"]
    if translator:
        title_parts.append(f" {translator}译")
    if route == "read":
        title_parts.append(" — 在线全文阅读 | 佛津 FoJin")
    else:
        title_parts.append(" — 佛津 FoJin")
    title = "".join(title_parts)

    desc_parts = [f"《{title_zh}》"]
    meta_bits = []
    if dynasty:
        meta_bits.append(dynasty)
    if translator:
        meta_bits.append(f"{translator}译")
    if cbeta_id:
        meta_bits.append(f"CBETA {cbeta_id}")
    if meta_bits:
        desc_parts.append("，" + "，".join(meta_bits))
    desc_parts.append(
        "。佛津 FoJin 数字佛典平台提供全文阅读、平行对照、AI 智能问答与原典引用。汉传、藏传、南传、梵文、巴利文多语种佛教文献聚合检索。"
    )
    description = "".join(desc_parts)

    base = str(request.base_url).rstrip("/")
    # base_url comes from the inbound request — under cloudflare/nginx the
    # forwarded scheme/host should already be set on the request.
    if route == "read":
        canonical = f"{base}/texts/{text.id}/read"
    else:
        canonical = f"{base}/texts/{text.id}"
    return title, description, canonical


async def _serve_text_seo_html(
    text_id: int,
    request: Request,
    db: AsyncSession,
    *,
    route: str,
    robots: str = "index, follow",
) -> HTMLResponse:
    text = await get_text_by_id(db, text_id)
    if text is None:
        raise HTTPException(status_code=404, detail="text not found")
    try:
        html = await _fetch_index_html()
    except httpx.HTTPError as e:
        logger.warning("Failed to fetch frontend index.html: %s", e)
        # Fall back to a minimal HTML so the bot still gets correct meta;
        # the user's browser would fail anyway since the bundle refs are
        # missing — but bots don't care about JS.
        title, description, canonical = _build_text_meta(text, request, route=route)
        fallback = (
            "<!doctype html><html><head>"
            f"<title>{_escape_meta_value(title)}</title>"
            f'<meta name="description" content="{_escape_meta_value(description)}" />'
            f'<meta name="robots" content="{_escape_meta_value(robots)}" />'
            f'<link rel="canonical" href="{_escape_meta_value(canonical)}" />'
            "</head><body></body></html>"
        )
        return HTMLResponse(content=fallback, status_code=200)

    title, description, canonical = _build_text_meta(text, request, route=route)
    return HTMLResponse(content=_inject_meta(html, title, description, canonical, robots=robots))


@router.get("/texts/{text_id}", response_class=HTMLResponse, include_in_schema=False)
async def text_detail_seo_html(text_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """SEO-friendly HTML for the text detail landing page (indexable)."""
    return await _serve_text_seo_html(text_id, request, db, route="detail")


@router.get("/texts/{text_id}/read", response_class=HTMLResponse, include_in_schema=False)
async def text_reader_seo_html(text_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """SEO-friendly HTML for the full-text reader page.

    Marked ``noindex, follow``: the reader page Googlebot sees is just the
    SPA shell (the actual text content only renders after the React bundle
    runs), so it duplicates the content-richer ``/texts/{id}`` detail page
    rendered by the Cloudflare prerender Worker. ``follow`` keeps internal
    link equity flowing back to the detail page.
    """
    return await _serve_text_seo_html(text_id, request, db, route="read", robots="noindex, follow")


# ── Shared Q&A SSR meta ──────────────────────────────────────


_MARKDOWN_FENCE_RE = re.compile(r"```[\s\S]*?```")
_MARKDOWN_INLINE_CODE_RE = re.compile(r"`([^`]*)`")
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MARKDOWN_HEADING_RE = re.compile(r"^\s*#{1,6}\s*", re.MULTILINE)
_MARKDOWN_EMPHASIS_RE = re.compile(r"[*_]{1,3}([^*_]+)[*_]{1,3}")
_CITATION_BRACKETS_RE = re.compile(r"【[^】]*】")
_WHITESPACE_RUN_RE = re.compile(r"\s+")


def _strip_markdown(text: str) -> str:
    """Best-effort markdown → plain text for the meta description.

    The shared Q&A answer is markdown; meta descriptions are short plain
    strings. We strip code fences, inline code, links, headings, and
    emphasis markers, drop ``【…】`` citation pills, and collapse
    whitespace.
    """
    cleaned = _MARKDOWN_FENCE_RE.sub("", text)
    cleaned = _MARKDOWN_INLINE_CODE_RE.sub(r"\1", cleaned)
    cleaned = _MARKDOWN_LINK_RE.sub(r"\1", cleaned)
    cleaned = _MARKDOWN_HEADING_RE.sub("", cleaned)
    cleaned = _MARKDOWN_EMPHASIS_RE.sub(r"\1", cleaned)
    cleaned = _CITATION_BRACKETS_RE.sub("", cleaned)
    return _WHITESPACE_RUN_RE.sub(" ", cleaned).strip()


def _truncate_for_meta(value: str, *, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _build_share_qa_meta(record: SharedQA, request: Request) -> dict[str, str]:
    """Compose meta values for ``/share/qa/{share_id}``."""
    question = (record.question or "").strip() or "佛学问答"
    title_question = _truncate_for_meta(question, limit=60)
    title = f"{title_question} - 佛津 AI 佛学问答"

    answer_plain = _strip_markdown(record.answer or "")
    description = _truncate_for_meta(answer_plain or question, limit=150)

    base = str(request.base_url).rstrip("/")
    canonical = f"{base}/share/qa/{record.id}"
    og_image = f"{base}/api/og/share/qa/{record.id}"
    return {
        "title": title,
        "description": description,
        "canonical": canonical,
        "og_title": title_question,
        "og_description": description,
        "og_image": og_image,
    }


_OG_TAG_PATTERNS = (
    re.compile(r'<meta\s+property="og:title"\s+content="[^"]*"\s*/?>', re.IGNORECASE),
    re.compile(r'<meta\s+property="og:description"\s+content="[^"]*"\s*/?>', re.IGNORECASE),
    re.compile(r'<meta\s+property="og:image"\s+content="[^"]*"\s*/?>', re.IGNORECASE),
    re.compile(r'<meta\s+property="og:image:width"\s+content="[^"]*"\s*/?>', re.IGNORECASE),
    re.compile(r'<meta\s+property="og:image:height"\s+content="[^"]*"\s*/?>', re.IGNORECASE),
    re.compile(r'<meta\s+property="og:type"\s+content="[^"]*"\s*/?>', re.IGNORECASE),
    re.compile(r'<meta\s+property="og:url"\s+content="[^"]*"\s*/?>', re.IGNORECASE),
    re.compile(r'<meta\s+name="twitter:card"\s+content="[^"]*"\s*/?>', re.IGNORECASE),
)


def _strip_existing_og_tags(html: str) -> str:
    """Remove any pre-existing og:* / twitter:card tags from index.html."""
    for pattern in _OG_TAG_PATTERNS:
        html = pattern.sub("", html)
    return html


def _inject_share_qa_meta(html: str, meta: dict[str, str]) -> str:
    """Inject share-Q&A specific meta tags into the SPA shell HTML.

    Reuses ``_inject_meta`` for ``<title>``, description, canonical, and
    robots; then appends og:* / twitter:card tags right before
    ``</head>`` so crawlers without JS see the per-question values
    instead of the homepage defaults.
    """
    new_html = _inject_meta(
        html,
        title=meta["title"],
        description=meta["description"],
        canonical_url=meta["canonical"],
        robots="index, follow",
    )
    new_html = _strip_existing_og_tags(new_html)
    og_tags = (
        f'<meta property="og:title" content="{_escape_meta_value(meta["og_title"])}" />\n'
        f'  <meta property="og:description" content="{_escape_meta_value(meta["og_description"])}" />\n'
        f'  <meta property="og:image" content="{_escape_meta_value(meta["og_image"])}" />\n'
        f'  <meta property="og:image:width" content="1200" />\n'
        f'  <meta property="og:image:height" content="630" />\n'
        f'  <meta property="og:type" content="article" />\n'
        f'  <meta property="og:url" content="{_escape_meta_value(meta["canonical"])}" />\n'
        f'  <meta name="twitter:card" content="summary_large_image" />\n  '
    )
    return _HEAD_CLOSE_RE.sub(f"  {og_tags}</head>", new_html, count=1)


@router.get("/share/qa/{share_id}", response_class=HTMLResponse, include_in_schema=False)
async def shared_qa_seo_html(share_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """SEO-friendly HTML for shared Q&A links.

    Public Q&A links used to inherit the homepage meta tags (generic
    title and a stock landscape og:image), so every link shared to
    linux.do / X / WeChat / Telegram looked identical and carried no
    information about the underlying question. This handler injects
    per-question title / description / canonical and points
    ``og:image`` at ``/api/og/share/qa/{id}`` for a dynamically
    rendered card.
    """
    record = await db.scalar(select(SharedQA).where(SharedQA.id == share_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Shared Q&A not found")

    meta = _build_share_qa_meta(record, request)
    try:
        html = await _fetch_index_html()
    except httpx.HTTPError as e:
        logger.warning("Failed to fetch frontend index.html for share/qa: %s", e)
        fallback = (
            "<!doctype html><html><head>"
            f"<title>{_escape_meta_value(meta['title'])}</title>"
            f'<meta name="description" content="{_escape_meta_value(meta["description"])}" />'
            f'<meta property="og:title" content="{_escape_meta_value(meta["og_title"])}" />'
            f'<meta property="og:description" content="{_escape_meta_value(meta["og_description"])}" />'
            f'<meta property="og:image" content="{_escape_meta_value(meta["og_image"])}" />'
            f'<meta property="og:type" content="article" />'
            f'<meta name="twitter:card" content="summary_large_image" />'
            f'<link rel="canonical" href="{_escape_meta_value(meta["canonical"])}" />'
            "</head><body></body></html>"
        )
        return HTMLResponse(content=fallback, status_code=200)

    return HTMLResponse(content=_inject_share_qa_meta(html, meta))
