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
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
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
_HEAD_CLOSE_RE = re.compile(r"</head>", re.IGNORECASE)


def _escape_meta_value(value: str) -> str:
    """Escape characters that would break out of an HTML attribute value."""
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


async def _fetch_index_html() -> str:
    """Fetch the built index.html from the frontend container with TTL caching."""
    now = time.monotonic()
    cached_at = _index_html_cache.get("ts")
    cached_html = _index_html_cache.get("html")
    if (
        isinstance(cached_at, float)
        and isinstance(cached_html, str)
        and now - cached_at < _INDEX_HTML_CACHE_TTL
    ):
        return cached_html

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(_FRONTEND_INDEX_URL)
        resp.raise_for_status()
        html = resp.text

    _index_html_cache["html"] = html
    _index_html_cache["ts"] = now
    return html


def _inject_meta(html: str, title: str, description: str, canonical_url: str) -> str:
    """Replace <title>, <meta name="description">, and <link rel="canonical">.

    If a canonical link is missing entirely (the default for the React SPA
    template), we add it just before the closing </head> tag.
    """
    safe_title = _escape_meta_value(title)
    safe_desc = _escape_meta_value(description)
    safe_canonical = _escape_meta_value(canonical_url)

    new_html = _TITLE_RE.sub(f"<title>{safe_title}</title>", html, count=1)
    new_html = _DESCRIPTION_RE.sub(
        f'<meta name="description" content="{safe_desc}" />',
        new_html,
        count=1,
    )
    canonical_tag = f'<link rel="canonical" href="{safe_canonical}" />'
    if _CANONICAL_RE.search(new_html):
        new_html = _CANONICAL_RE.sub(canonical_tag, new_html, count=1)
    else:
        new_html = _HEAD_CLOSE_RE.sub(f"  {canonical_tag}\n  </head>", new_html, count=1)
    return new_html


def _build_text_meta(text, request: Request) -> tuple[str, str, str]:
    """Compose the per-text title, description, and canonical URL."""
    title_zh = text.title_zh or "佛典"
    translator = (text.translator or "").strip()
    dynasty = (text.dynasty or "").strip()
    cbeta_id = (text.cbeta_id or "").strip()

    title_parts = [f"《{title_zh}》"]
    if translator:
        title_parts.append(f" {translator}译")
    title_parts.append(" — 在线全文阅读 | 佛津 FoJin")
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
    desc_parts.append("。佛津 FoJin 数字佛典平台提供全文阅读、平行对照、AI 智能问答与原典引用。汉传、藏传、南传、梵文、巴利文多语种佛教文献聚合检索。")
    description = "".join(desc_parts)

    base = str(request.base_url).rstrip("/")
    # base_url comes from the inbound request — under cloudflare/nginx the
    # forwarded scheme/host should already be set on the request.
    canonical = f"{base}/texts/{text.id}/read"
    return title, description, canonical


async def _serve_text_seo_html(text_id: int, request: Request, db: AsyncSession) -> HTMLResponse:
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
        title, description, canonical = _build_text_meta(text, request)
        fallback = (
            "<!doctype html><html><head>"
            f"<title>{_escape_meta_value(title)}</title>"
            f'<meta name="description" content="{_escape_meta_value(description)}" />'
            f'<link rel="canonical" href="{_escape_meta_value(canonical)}" />'
            "</head><body></body></html>"
        )
        return HTMLResponse(content=fallback, status_code=200)

    title, description, canonical = _build_text_meta(text, request)
    return HTMLResponse(content=_inject_meta(html, title, description, canonical))


@router.get("/texts/{text_id}", response_class=HTMLResponse, include_in_schema=False)
async def text_detail_seo_html(text_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """SEO-friendly HTML for the text detail landing page."""
    return await _serve_text_seo_html(text_id, request, db)


@router.get("/texts/{text_id}/read", response_class=HTMLResponse, include_in_schema=False)
async def text_reader_seo_html(text_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """SEO-friendly HTML for the full-text reader page."""
    return await _serve_text_seo_html(text_id, request, db)
