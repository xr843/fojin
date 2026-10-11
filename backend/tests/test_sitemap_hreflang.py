"""sitemap 的三语 xhtml:link 互指（docs/superpowers/specs/2026-10-11-i18n-seo-design.md）。

只有真有语言版本的页面才互指：/search（结果页不收录、robots 挡）与 /agents
（无多语）不加；辞典 / 人物 sitemap 不变——那两类页面不做语言版本。
"""

import re
from contextlib import asynccontextmanager

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import sitemap


async def _get(path: str) -> str:
    app = FastAPI()
    app.include_router(sitemap.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fojin.app") as client:
        resp = await client.get(path)
    assert resp.status_code == 200
    return resp.text


def _url_block(xml: str, loc: str) -> str:
    return re.search(rf"<url>\s*<loc>{re.escape(loc)}</loc>.*?</url>", xml, re.S).group(0)


async def test_static_sitemap_has_alternates():
    xml = await _get("/sitemap-static.xml")
    assert 'xmlns:xhtml="http://www.w3.org/1999/xhtml"' in xml
    chat = _url_block(xml, "https://fojin.app/chat")
    assert '<xhtml:link rel="alternate" hreflang="zh-Hans" href="https://fojin.app/chat"/>' in chat
    assert '<xhtml:link rel="alternate" hreflang="zh-Hant" href="https://fojin.app/chat?lang=zh-Hant"/>' in chat
    assert '<xhtml:link rel="alternate" hreflang="en" href="https://fojin.app/chat?lang=en"/>' in chat
    assert '<xhtml:link rel="alternate" hreflang="x-default" href="https://fojin.app/chat"/>' in chat
    home = _url_block(xml, "https://fojin.app/")
    assert '<xhtml:link rel="alternate" hreflang="en" href="https://fojin.app/?lang=en"/>' in home
    for loc in ("https://fojin.app/search", "https://fojin.app/agents"):
        assert "xhtml:link" not in _url_block(xml, loc)


async def test_texts_sitemap_has_alternates(monkeypatch):
    @asynccontextmanager
    async def fake_session():
        yield None

    async def fake_texts(session):
        return [(1, "2026-03-01"), (2, "2026-03-01")]

    monkeypatch.setattr(sitemap, "async_session", fake_session)
    monkeypatch.setattr(sitemap, "get_all_text_ids_with_dates", fake_texts)
    xml = await _get("/sitemap-texts-0.xml")
    assert 'xmlns:xhtml="http://www.w3.org/1999/xhtml"' in xml
    assert xml.count('hreflang="en"') == 2
    assert '<xhtml:link rel="alternate" hreflang="en" href="https://fojin.app/texts/1?lang=en"/>' in xml
