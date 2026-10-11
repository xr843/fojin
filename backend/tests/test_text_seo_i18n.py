"""三语经文详情页：html lang / title / canonical / hreflang / og:locale。

见 docs/superpowers/specs/2026-10-11-i18n-seo-design.md。上线前 Googlebot 抓
``/texts/235?lang=en`` 拿到的是 ``<html lang="zh-CN">`` + 简体标题 + 指回简体页的
canonical，于是英文 / 繁体版本统统被并进简体页。
"""

import re
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import seo
from app.database import get_db

# Mirrors the head of the real frontend/index.html (the parts _inject_meta touches).
SHELL = (
    '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n'
    "<title>x</title>\n"
    '<meta name="description" content="x" />\n'
    '<meta name="robots" content="index, follow" />\n'
    '<link rel="canonical" href="https://fojin.app/" />\n'
    '<meta property="og:title" content="x" />\n'
    '<meta property="og:description" content="x" />\n'
    '<meta property="og:url" content="https://fojin.app/" />\n'
    '<meta property="og:locale" content="zh_CN" />\n'
    '<meta name="twitter:title" content="x" />\n'
    '<meta name="twitter:description" content="x" />\n'
    '</head><body><div id="root"></div></body></html>'
)
TEXT = SimpleNamespace(
    id=235,
    title_zh="般若波羅蜜多心經",
    translator="玄奘",
    dynasty="唐",
    cbeta_id="T0251",
    lang="lzh",
    title_en="Heart Sutra",
    title_sa=None,
    title_pi=None,
    title_bo=None,
)


@pytest.fixture
def fetched(monkeypatch):
    calls: list[str] = []

    async def fake_fetch(suffix: str = "") -> str:
        calls.append(suffix)
        return SHELL

    async def fake_get_text(db, text_id):
        return TEXT

    async def fake_body(db, text_id):
        return {"excerpt": "觀自在菩薩", "juans": [1, 2], "total_juans": 2}

    monkeypatch.setattr(seo, "_fetch_index_html", fake_fetch)
    monkeypatch.setattr(seo, "get_text_by_id", fake_get_text)
    monkeypatch.setattr(seo, "_fetch_text_seo_body", fake_body)
    return calls


async def _get(url: str) -> str:
    app = FastAPI()
    app.include_router(seo.router)

    async def no_db():
        yield None

    app.dependency_overrides[get_db] = no_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fojin.app") as client:
        resp = await client.get(url, headers={"X-Forwarded-Proto": "https"})
    assert resp.status_code == 200
    return resp.text


def _title(html: str) -> str:
    return re.search(r"<title>([^<]*)</title>", html).group(1)


@pytest.mark.parametrize(
    ("qs", "html_lang", "canonical", "og_locale", "suffix"),
    [
        ("", "zh-Hans", "https://fojin.app/texts/235", "zh_CN", ""),
        ("?lang=zh-Hant", "zh-Hant", "https://fojin.app/texts/235?lang=zh-Hant", "zh_TW", ".zh-Hant"),
        ("?lang=en", "en", "https://fojin.app/texts/235?lang=en", "en_US", ".en"),
        ("?lang=xyz", "zh-Hans", "https://fojin.app/texts/235", "zh_CN", ""),
    ],
)
async def test_detail_page_per_language(fetched, qs, html_lang, canonical, og_locale, suffix):
    html = await _get(f"/texts/235{qs}")
    assert f'<html lang="{html_lang}">' in html
    assert f'<link rel="canonical" href="{canonical}" />' in html
    assert f'<meta property="og:url" content="{canonical}" />' in html
    assert f'<meta property="og:locale" content="{og_locale}" />' in html
    assert html.count('rel="alternate" hreflang=') == 4
    assert '<link rel="alternate" hreflang="zh-Hant" href="https://fojin.app/texts/235?lang=zh-Hant" />' in html
    assert '<link rel="alternate" hreflang="x-default" href="https://fojin.app/texts/235" />' in html
    assert fetched == [suffix]


async def test_simplified_title_pairs_both_scripts(fetched):
    title = _title(await _get("/texts/235"))
    assert title == "《般若波罗蜜多心经（般若波羅蜜多心經）》 玄奘译 — 佛津 FoJin"


async def test_traditional_copy(fetched):
    html = await _get("/texts/235?lang=zh-Hant")
    assert _title(html) == "《般若波羅蜜多心經》 玄奘譯 — 佛津 FoJin"
    assert "數位佛典平台" in html
    assert "卷目錄" in html and "閱讀全文" in html
    assert "卷目录" not in html


async def test_english_copy(fetched):
    html = await _get("/texts/235?lang=en")
    assert _title(html) == "《般若波羅蜜多心經》 trans. 玄奘 — FoJin"
    assert "Read the full text on FoJin" in html
    assert "Fascicles" in html and "Fascicle 2" in html
    assert '"name":"Texts"' in html  # breadcrumb
    assert "卷目录" not in html and "佛典阅读" not in html


async def test_reader_page_is_not_localised(fetched):
    html = await _get("/texts/235/read?lang=en")
    assert '<html lang="zh-Hans">' in html
    assert "hreflang=" not in html
    assert '<link rel="canonical" href="https://fojin.app/texts/235/read" />' in html
    assert fetched == [""]
