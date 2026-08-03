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

import json
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
from app.models.text import TextContent
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
_ROOT_DIV_RE = re.compile(r'<div\s+id="root"\s*></div>', re.IGNORECASE)

# Open Graph / Twitter equivalents of the three tags above. Without these the
# injected page keeps the SPA template's homepage og:* values, so *sharing any
# text or shared-QA link posts a card advertising the homepage* — wrong title,
# and an og:url that sends the reader to `/` instead of the thing being shared.
_OG_TITLE_RE = re.compile(r'<meta\s+property="og:title"\s+content="[^"]*"\s*/?>', re.IGNORECASE)
_OG_DESCRIPTION_RE = re.compile(r'<meta\s+property="og:description"\s+content="[^"]*"\s*/?>', re.IGNORECASE)
_OG_URL_RE = re.compile(r'<meta\s+property="og:url"\s+content="[^"]*"\s*/?>', re.IGNORECASE)
_TW_TITLE_RE = re.compile(r'<meta\s+name="twitter:title"\s+content="[^"]*"\s*/?>', re.IGNORECASE)
_TW_DESCRIPTION_RE = re.compile(r'<meta\s+name="twitter:description"\s+content="[^"]*"\s*/?>', re.IGNORECASE)

# Cap on how much text we inject into the SEO HTML body. Googlebot weighs the
# *first* ~2000 chars heaviest; injecting much more than this hits diminishing
# returns and inflates page weight for real users (the SEO block is rendered
# inside <noscript>, which Googlebot indexes but real browsers ignore).
_SEO_BODY_CHAR_LIMIT = 1200
_SEO_JUAN_LIST_LIMIT = 50


def _escape_meta_value(value: str) -> str:
    """Escape characters that would break out of an HTML attribute value.

    The backslash is escaped for a second, non-obvious reason: these values are
    spliced into the shell via ``re.sub``, whose *replacement template* itself
    interprets escape sequences. Without this, ``\\074`` would survive this
    function untouched and re-materialise as ``<`` after substitution. The
    call sites now use callable replacements (which disable template parsing
    entirely), so this is defence in depth against that being undone.

    ``&`` must stay first so the entities emitted below aren't double-escaped.
    """
    return (
        value.replace("&", "&amp;")
        .replace("\\", "&#92;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("'", "&#39;")
    )


def public_base_url(request: Request) -> str:
    """Base URL as the *outside world* sees it, i.e. with the real scheme.

    ``request.base_url`` reports the scheme of the connection uvicorn actually
    accepted. Behind our nginx hop that is always ``http``, so every URL built
    from it went out as ``http://`` — og:url, the JSON-LD ``url``, and every
    breadcrumb item. Cloudflare's Automatic HTTPS Rewrites then silently
    patched only the ``href``-bearing ``<link rel="canonical">``, leaving the
    page self-contradictory: canonical said https, og:url said http, and the
    sitemap (which hardcodes https) disagreed with both.

    nginx sets ``X-Forwarded-Proto`` with ``proxy_set_header``, which
    OVERWRITES any client-supplied value, so unlike ``X-Forwarded-For`` (which
    is *appended* to — see backend/entrypoint.sh for why we deliberately do not
    run uvicorn with ``--proxy-headers``) this header cannot be spoofed through
    the proxy and is safe to trust. Values other than http/https are ignored.
    """
    base = str(request.base_url).rstrip("/")
    forwarded = request.headers.get("x-forwarded-proto", "")
    scheme = forwarded.split(",")[0].strip().lower()
    if scheme in ("http", "https"):
        base = re.sub(r"^https?://", f"{scheme}://", base, count=1)
    return base


def _sub_literal(pattern: re.Pattern[str], replacement: str, html: str, *, count: int = 1) -> str:
    """``pattern.sub`` that treats ``replacement`` as a literal string.

    Passing a plain string to ``re.sub`` makes it a *replacement template*:
    ``\\1`` is a group reference (and raises ``re.error`` when the pattern has
    no such group), and ``\\074`` is an octal character escape that runs
    *after* our HTML escaping. Since every replacement here embeds
    user-controlled text, a callable — which ``re`` never parses — is the
    only safe form.
    """
    return pattern.sub(lambda _match: replacement, html, count=count)


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
    """Replace title / description / canonical / robots **and the og:* + twitter:* mirrors**.

    The Open Graph tags matter as much as ``<title>`` here: they are what a
    WeChat or Twitter share card renders. Leaving the template's values in
    place meant every shared text — and every shared QA, which is the entire
    point of ``/share/qa/{id}`` — posted a card titled after the homepage,
    with an ``og:url`` pointing at ``/`` rather than the thing being shared.

    ``og:image`` is deliberately NOT touched: there is no per-text image, so
    the site-wide share card is the correct asset.

    If a canonical link is missing entirely (the default for the React SPA
    template), we add it just before the closing </head> tag.
    """
    safe_title = _escape_meta_value(title)
    safe_desc = _escape_meta_value(description)
    safe_canonical = _escape_meta_value(canonical_url)
    safe_robots = _escape_meta_value(robots)

    new_html = _sub_literal(_TITLE_RE, f"<title>{safe_title}</title>", html)
    new_html = _sub_literal(
        _DESCRIPTION_RE,
        f'<meta name="description" content="{safe_desc}" />',
        new_html,
    )
    new_html = _sub_literal(
        _ROBOTS_RE,
        f'<meta name="robots" content="{safe_robots}" />',
        new_html,
    )
    for pattern, replacement in (
        (_OG_TITLE_RE, f'<meta property="og:title" content="{safe_title}" />'),
        (_OG_DESCRIPTION_RE, f'<meta property="og:description" content="{safe_desc}" />'),
        (_OG_URL_RE, f'<meta property="og:url" content="{safe_canonical}" />'),
        (_TW_TITLE_RE, f'<meta name="twitter:title" content="{safe_title}" />'),
        (_TW_DESCRIPTION_RE, f'<meta name="twitter:description" content="{safe_desc}" />'),
    ):
        new_html = _sub_literal(pattern, replacement, new_html)
    canonical_tag = f'<link rel="canonical" href="{safe_canonical}" />'
    if _CANONICAL_RE.search(new_html):
        new_html = _sub_literal(_CANONICAL_RE, canonical_tag, new_html)
    else:
        new_html = _sub_literal(_HEAD_CLOSE_RE, f"  {canonical_tag}\n  </head>", new_html)
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

    base = public_base_url(request)
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
    patched = _inject_meta(html, title, description, canonical, robots=robots)
    patched = _inject_text_jsonld(patched, _build_text_jsonld(text, canonical_url=canonical))

    # Detail route is the indexable surface — give Googlebot a real body.
    # Reader route stays a SPA shell (it's noindex anyway).
    if route == "detail":
        base_url = public_base_url(request)
        patched = _inject_text_jsonld(
            patched, _build_breadcrumb_jsonld(text, canonical_url=canonical, base_url=base_url)
        )
        try:
            body = await _fetch_text_seo_body(db, text.id)
        except Exception as e:  # body is best-effort — never block detail render
            logger.warning("SEO body fetch failed for text %s: %s", text.id, e)
            body = {"excerpt": "", "juans": [], "total_juans": 0}
        seo_block = _render_text_seo_body(text, body, base_url=base_url)
        if _ROOT_DIV_RE.search(patched):
            patched = _sub_literal(_ROOT_DIV_RE, f'<div id="root"></div>\n{seo_block}', patched)
        else:
            patched = patched.replace("</body>", f"{seo_block}\n</body>", 1)
    return HTMLResponse(content=patched)


# Languages that buddhist_texts.lang uses, mapped to BCP-47 codes that
# schema.org / search engines understand. ``lzh`` (literary Chinese) is the
# only one that requires translation; the rest are already valid BCP-47.
_LANG_TO_BCP47 = {
    "lzh": "lzh",  # already a registered IANA subtag for Literary Chinese
    "zh": "zh-Hant",
    "pi": "pi",
    "bo": "bo",
    "sa": "sa",
    "en": "en",
    "ja": "ja",
    "ko": "ko",
}


def _build_text_jsonld(text, *, canonical_url: str) -> dict:
    """Build a schema.org Book entry for a Buddhist canonical text.

    Crawlers and Google Scholar consume this to decide *what* the page is
    about, beyond what \\<title\\> / meta description carry. We populate the
    fields with the strongest signal we have — CBETA identifier, translator
    if known, dynasty as a publication date approximation, language code.
    """
    title_zh = (text.title_zh or "").strip()
    translator = (text.translator or "").strip()
    dynasty = (text.dynasty or "").strip()
    cbeta_id = (text.cbeta_id or "").strip()
    lang = (text.lang or "lzh").strip().lower()

    payload: dict = {
        "@context": "https://schema.org",
        "@type": "Book",
        "name": title_zh or "佛典",
        "url": canonical_url,
        "inLanguage": _LANG_TO_BCP47.get(lang, lang),
        "isAccessibleForFree": True,
    }
    if translator:
        payload["translator"] = {"@type": "Person", "name": translator}
    if dynasty:
        # ``datePublished`` is meant to be ISO-8601, but a free-form era
        # string ("唐"/"宋"/...) is what we have and is what Google's
        # structured-data tester accepts gracefully.
        payload["datePublished"] = dynasty
    if cbeta_id:
        payload["identifier"] = {
            "@type": "PropertyValue",
            "propertyID": "CBETA",
            "value": cbeta_id,
        }
    # Title transliterations into other scripts when available.
    alt_names = [
        getattr(text, "title_en", None),
        getattr(text, "title_sa", None),
        getattr(text, "title_pi", None),
        getattr(text, "title_bo", None),
    ]
    alt_names = [n for n in alt_names if n]
    if alt_names:
        payload["alternateName"] = alt_names
    payload["publisher"] = {
        "@type": "Organization",
        "name": "佛津 FoJin",
        "url": "https://fojin.app",
    }
    return payload


def _build_breadcrumb_jsonld(text, *, canonical_url: str, base_url: str) -> dict:
    """BreadcrumbList JSON-LD so Google renders the path in rich results.

    Home › 全文检索 › {经名} maps the user's mental model better than the
    raw URL and is documented to lift CTR ~25% on Google search results.
    """
    title_zh = (text.title_zh or "").strip() or "佛典"
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "佛津 FoJin", "item": base_url},
            {"@type": "ListItem", "position": 2, "name": "佛典阅读", "item": f"{base_url}/sources"},
            {"@type": "ListItem", "position": 3, "name": f"《{title_zh}》", "item": canonical_url},
        ],
    }


async def _fetch_text_seo_body(db: AsyncSession, text_id: int) -> dict:
    """Pull the first chunk of canonical text + juan TOC for SEO body injection.

    Returns a dict with ``excerpt`` (first ~1200 chars of juan 1, lightly
    cleaned) and ``juan_count`` (how many juan exist). The excerpt is what
    Googlebot will see inside <noscript>; real users see the React-rendered
    reader instead.
    """
    excerpt_row = await db.execute(
        select(TextContent.content)
        .where(TextContent.text_id == text_id)
        .order_by(TextContent.juan_num.asc(), TextContent.id.asc())
        .limit(1)
    )
    raw = excerpt_row.scalar_one_or_none() or ""
    cleaned = _WHITESPACE_RUN_RE.sub(" ", raw).strip()
    if len(cleaned) > _SEO_BODY_CHAR_LIMIT:
        cleaned = cleaned[: _SEO_BODY_CHAR_LIMIT - 1].rstrip() + "…"

    count_row = await db.execute(select(TextContent.juan_num).where(TextContent.text_id == text_id).distinct())
    juans = sorted({r[0] for r in count_row.all() if r[0] is not None})
    return {"excerpt": cleaned, "juans": juans[:_SEO_JUAN_LIST_LIMIT], "total_juans": len(juans)}


def _render_text_seo_body(text, body: dict, *, base_url: str) -> str:
    """Render the <noscript> SEO block inserted just after <body>.

    The block contains: title, basic metadata, an excerpt of the canonical
    text, juan TOC, and breadcrumb links. ``<noscript>`` is the cleanest
    container because Googlebot indexes its content (per JS-disabled
    fallback semantics) while real browsers with JS enabled ignore it
    entirely — no flicker, no double-rendering, no cloaking.
    """
    title_zh = (text.title_zh or "佛典").strip()
    translator = (text.translator or "").strip()
    dynasty = (text.dynasty or "").strip()
    cbeta_id = (text.cbeta_id or "").strip()

    parts = ['<noscript><div id="seo-content">']
    parts.append(f"<h1>《{_escape_meta_value(title_zh)}》</h1>")
    meta_bits = []
    if dynasty:
        meta_bits.append(_escape_meta_value(dynasty))
    if translator:
        meta_bits.append(f"{_escape_meta_value(translator)}译")
    if cbeta_id:
        meta_bits.append(f"CBETA {_escape_meta_value(cbeta_id)}")
    if meta_bits:
        parts.append("<p>" + " · ".join(meta_bits) + "</p>")

    if body.get("excerpt"):
        parts.append(f"<p>{_escape_meta_value(body['excerpt'])}</p>")

    juans = body.get("juans") or []
    if len(juans) > 1:
        parts.append("<h2>卷目录</h2><ul>")
        for j in juans:
            parts.append(f'<li><a href="{base_url}/texts/{text.id}/read?juan={int(j)}">第 {int(j)} 卷</a></li>')
        if body.get("total_juans", 0) > _SEO_JUAN_LIST_LIMIT:
            parts.append(f"<li>…共 {body['total_juans']} 卷</li>")
        parts.append("</ul>")

    parts.append(
        f'<p><a href="{base_url}/texts/{text.id}/read">阅读全文 »</a> · '
        f'<a href="{base_url}/sources">浏览全部佛典</a></p>'
    )
    parts.append("</div></noscript>")
    return "".join(parts)


def _inject_text_jsonld(html: str, payload: dict) -> str:
    """Insert a single \\<script type=\"application/ld+json\"\\> just before \\</head\\>.

    ``json.dumps`` does the escaping. We additionally guard against
    ``</script>`` appearing inside the payload (technically impossible from
    the fields we feed it, but cheap insurance).
    """
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    tag = f'<script type="application/ld+json">{blob}</script>'
    return _sub_literal(_HEAD_CLOSE_RE, f"  {tag}\n  </head>", html)


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

    base = public_base_url(request)
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
    # First three reuse the named patterns defined near the top — the share-QA
    # path strips exactly the tags the text path rewrites, and two copies of
    # these regexes would drift apart the first time one side is edited.
    _OG_TITLE_RE,
    _OG_DESCRIPTION_RE,
    re.compile(r'<meta\s+property="og:image"\s+content="[^"]*"\s*/?>', re.IGNORECASE),
    re.compile(r'<meta\s+property="og:image:width"\s+content="[^"]*"\s*/?>', re.IGNORECASE),
    re.compile(r'<meta\s+property="og:image:height"\s+content="[^"]*"\s*/?>', re.IGNORECASE),
    re.compile(r'<meta\s+property="og:type"\s+content="[^"]*"\s*/?>', re.IGNORECASE),
    _OG_URL_RE,
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
    return _sub_literal(_HEAD_CLOSE_RE, f"  {og_tags}</head>", new_html)


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
