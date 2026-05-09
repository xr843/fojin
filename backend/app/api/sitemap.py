"""Dynamic sitemap.xml endpoints for SEO."""

import math
from datetime import date

from fastapi import APIRouter, Response
from fastapi.responses import Response as FastAPIResponse
from sqlalchemy import select

from app.database import async_session
from app.models.knowledge_graph import KGEntity
from app.services.text import get_all_text_ids_with_dates

router = APIRouter(tags=["sitemap"])

BASE_URL = "https://fojin.app"
TEXTS_PER_BATCH = 40_000
PERSONS_PER_BATCH = 20_000

STATIC_PAGES = [
    ("/", "daily", "1.0"),
    ("/search", "daily", "0.9"),
    ("/sources", "weekly", "0.8"),
    ("/dictionary", "weekly", "0.8"),
    ("/collections", "weekly", "0.7"),
    ("/topics", "weekly", "0.8"),
    ("/kg", "weekly", "0.7"),
    ("/chat", "weekly", "0.6"),
    # Sutra landing pages
    ("/sutras/heart-sutra", "monthly", "0.9"),
    ("/sutras/diamond-sutra", "monthly", "0.9"),
    ("/sutras/lotus-sutra", "monthly", "0.9"),
    ("/sutras/avatamsaka-sutra", "monthly", "0.9"),
    ("/sutras/shurangama-sutra", "monthly", "0.9"),
    ("/sutras/amitabha-sutra", "monthly", "0.9"),
    ("/sutras/ksitigarbha-sutra", "monthly", "0.9"),
    ("/sutras/medicine-buddha-sutra", "monthly", "0.9"),
    ("/sutras/platform-sutra", "monthly", "0.9"),
    ("/sutras/vimalakirti-sutra", "monthly", "0.9"),
]


def _xml_response(content: str) -> Response:
    return Response(
        content=content,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


async def _get_person_count(session) -> int:
    from sqlalchemy import func
    result = await session.execute(
        select(func.count(KGEntity.id)).where(KGEntity.entity_type == "person")
    )
    return result.scalar() or 0


@router.api_route("/sitemap.xml", methods=["GET", "HEAD"])
async def sitemap_index() -> Response:
    """Sitemap index pointing to sub-sitemaps."""
    async with async_session() as session:
        texts = await get_all_text_ids_with_dates(session)
        person_count = await _get_person_count(session)

    text_batches = max(1, math.ceil(len(texts) / TEXTS_PER_BATCH))
    person_batches = max(1, math.ceil(person_count / PERSONS_PER_BATCH)) if person_count else 0

    sitemaps = ['<?xml version="1.0" encoding="UTF-8"?>']
    sitemaps.append('<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    sitemaps.append(f"  <sitemap><loc>{BASE_URL}/sitemap-static.xml</loc></sitemap>")
    for i in range(text_batches):
        sitemaps.append(f"  <sitemap><loc>{BASE_URL}/sitemap-texts-{i}.xml</loc></sitemap>")
    for i in range(person_batches):
        sitemaps.append(f"  <sitemap><loc>{BASE_URL}/sitemap-persons-{i}.xml</loc></sitemap>")
    sitemaps.append("</sitemapindex>")

    return _xml_response("\n".join(sitemaps))


@router.api_route("/sitemap-static.xml", methods=["GET", "HEAD"])
async def sitemap_static() -> Response:
    """Static pages sitemap with today's date as lastmod hint."""
    today = date.today().isoformat()
    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for path, changefreq, priority in STATIC_PAGES:
        lines.append("  <url>")
        lines.append(f"    <loc>{BASE_URL}{path}</loc>")
        lines.append(f"    <lastmod>{today}</lastmod>")
        lines.append(f"    <changefreq>{changefreq}</changefreq>")
        lines.append(f"    <priority>{priority}</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")

    return _xml_response("\n".join(lines))


@router.api_route("/sitemap-persons-{batch}.xml", methods=["GET", "HEAD"])
async def sitemap_persons(batch: int) -> FastAPIResponse:
    """KG ``person`` entity sitemap, paginated by batch number.

    Backed by ``app.api.seo_persons.person_seo_html`` — these URLs were
    invisible to search engines until 2026-05; cumulatively they are the
    largest single content surface FoJin offers.
    """
    if batch < 0:
        return Response(content="Not Found", status_code=404)

    offset = batch * PERSONS_PER_BATCH
    async with async_session() as session:
        rows = await session.execute(
            select(KGEntity.id, KGEntity.created_at)
            .where(KGEntity.entity_type == "person")
            .order_by(KGEntity.id.asc())
            .offset(offset)
            .limit(PERSONS_PER_BATCH)
        )
        batch_persons = rows.all()

    if not batch_persons:
        return Response(content="Not Found", status_code=404)

    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for pid, created_at in batch_persons:
        lastmod = created_at.strftime("%Y-%m-%d") if created_at else date.today().isoformat()
        lines.append("  <url>")
        lines.append(f"    <loc>{BASE_URL}/persons/{pid}</loc>")
        lines.append(f"    <lastmod>{lastmod}</lastmod>")
        lines.append("    <changefreq>monthly</changefreq>")
        lines.append("    <priority>0.5</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")

    return _xml_response("\n".join(lines))


@router.api_route("/sitemap-texts-{batch}.xml", methods=["GET", "HEAD"])
async def sitemap_texts(batch: int) -> FastAPIResponse:
    """Text pages sitemap, paginated by batch number."""
    if batch < 0:
        return Response(content="Not Found", status_code=404)

    async with async_session() as session:
        texts = await get_all_text_ids_with_dates(session)

    start = batch * TEXTS_PER_BATCH
    if start >= len(texts):
        return Response(content="Not Found", status_code=404)

    end = min(start + TEXTS_PER_BATCH, len(texts))
    batch_texts = texts[start:end]

    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for text_id, date_str in batch_texts:
        lines.append("  <url>")
        lines.append(f"    <loc>{BASE_URL}/texts/{text_id}</loc>")
        lines.append(f"    <lastmod>{date_str}</lastmod>")
        lines.append("    <changefreq>monthly</changefreq>")
        lines.append("    <priority>0.6</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")

    return _xml_response("\n".join(lines))
