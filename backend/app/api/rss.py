"""RSS 2.0 feed for recently added Buddhist texts."""

from fastapi import APIRouter, Response
from sqlalchemy import select

from app.database import async_session
from app.models.text import BuddhistText

router = APIRouter(tags=["rss"])

BASE_URL = "https://fojin.app"


@router.api_route("/feed.xml", methods=["GET", "HEAD"])
async def rss_feed() -> Response:
    """RSS 2.0 feed of the 50 most recently added texts."""
    async with async_session() as session:
        result = await session.execute(
            select(BuddhistText)
            .order_by(BuddhistText.created_at.desc())
            .limit(50)
        )
        texts = result.scalars().all()

    items = []
    for t in texts:
        desc_parts = []
        if t.translator:
            desc_parts.append(f"译者: {t.translator}")
        if t.dynasty:
            desc_parts.append(f"朝代: {t.dynasty}")
        if t.category:
            desc_parts.append(f"分类: {t.category}")
        description = " · ".join(desc_parts) if desc_parts else t.title_zh

        title = _xml_escape(t.title_zh)
        description = _xml_escape(description)

        items.append(
            f"    <item>\n"
            f"      <title>{title}</title>\n"
            f"      <link>{BASE_URL}/texts/{t.id}</link>\n"
            f'      <guid isPermaLink="true">{BASE_URL}/texts/{t.id}</guid>\n'
            f"      <description>{description}</description>\n"
            f"      <pubDate>{t.created_at.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>\n"
            f"    </item>"
        )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        "    <title>佛津 FoJin — 最新收录</title>\n"
        f"    <link>{BASE_URL}</link>\n"
        "    <description>全球佛教古籍数字资源聚合平台 — 最新收录的经典</description>\n"
        "    <language>zh-CN</language>\n"
        f'    <atom:link href="{BASE_URL}/feed.xml" rel="self" type="application/rss+xml" />\n'
        + "\n".join(items)
        + "\n  </channel>\n"
        "</rss>"
    )

    return Response(
        content=xml,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


def _xml_escape(s: str) -> str:
    """Escape XML special characters."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
