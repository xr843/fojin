"""Tests for the schema.org Book JSON-LD injected into /texts/{id} responses.

Crawlers and Google Scholar parse this script tag to learn what the page
is about beyond the title / meta description. The fields populated here
are the strongest structured signal we have for each canonical text.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api import seo as seo_module


class _StubText:
    """Minimal stand-in for the buddhist_texts row used by the SEO route."""

    def __init__(
        self,
        *,
        id: int = 9,
        title_zh: str = "般若波羅蜜多心經",
        translator: str = "玄奘",
        dynasty: str = "唐",
        cbeta_id: str = "T0251",
        lang: str = "lzh",
        title_en: str | None = "Heart Sutra",
        title_sa: str | None = "Prajñāpāramitāhṛdaya",
        title_pi: str | None = None,
        title_bo: str | None = None,
    ):
        self.id = id
        self.title_zh = title_zh
        self.translator = translator
        self.dynasty = dynasty
        self.cbeta_id = cbeta_id
        self.lang = lang
        self.title_en = title_en
        self.title_sa = title_sa
        self.title_pi = title_pi
        self.title_bo = title_bo


@pytest_asyncio.fixture
async def seo_client():
    """Async client with backend deps stubbed; no real PG / ES / Redis."""
    with (
        patch("app.core.elasticsearch.init_es", new_callable=AsyncMock),
        patch("app.core.elasticsearch.close_es", new_callable=AsyncMock),
        patch("app.main.aioredis") as mock_redis_mod,
    ):
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_redis_mod.from_url.return_value = mock_redis

        from app.database import get_db
        from app.main import app

        async def fake_get_db():
            yield AsyncMock()

        app.dependency_overrides[get_db] = fake_get_db
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac
        finally:
            app.dependency_overrides.pop(get_db, None)


def _extract_jsonld(html: str) -> dict:
    """Pull the first ld+json script body out of the HTML and parse it."""
    import re

    m = re.search(r'<script type="application/ld\+json">(.+?)</script>', html, re.DOTALL)
    assert m is not None, f"no ld+json script found in: {html[:500]}"
    return json.loads(m.group(1))


def test_build_text_jsonld_populates_all_known_fields():
    text = _StubText()
    payload = seo_module._build_text_jsonld(text, canonical_url="https://fojin.app/texts/9")
    assert payload["@context"] == "https://schema.org"
    assert payload["@type"] == "Book"
    assert payload["name"] == "般若波羅蜜多心經"
    assert payload["url"] == "https://fojin.app/texts/9"
    assert payload["inLanguage"] == "lzh"
    assert payload["isAccessibleForFree"] is True
    assert payload["translator"] == {"@type": "Person", "name": "玄奘"}
    assert payload["datePublished"] == "唐"
    assert payload["identifier"] == {
        "@type": "PropertyValue",
        "propertyID": "CBETA",
        "value": "T0251",
    }
    # Alt names from non-empty title_* fields, in deterministic order.
    assert payload["alternateName"] == ["Heart Sutra", "Prajñāpāramitāhṛdaya"]
    assert payload["publisher"]["name"] == "佛津 FoJin"


def test_build_text_jsonld_omits_unknown_fields_gracefully():
    text = _StubText(
        translator="",
        dynasty="",
        cbeta_id="",
        title_en=None,
        title_sa=None,
    )
    payload = seo_module._build_text_jsonld(text, canonical_url="https://x/y")
    assert "translator" not in payload
    assert "datePublished" not in payload
    assert "identifier" not in payload
    assert "alternateName" not in payload
    # name still falls through with a sensible default.
    assert payload["name"]


def test_build_text_jsonld_falls_back_for_empty_title():
    text = _StubText(title_zh="")
    payload = seo_module._build_text_jsonld(text, canonical_url="https://x/y")
    assert payload["name"] == "佛典"


@pytest.mark.anyio
async def test_text_seo_html_contains_book_jsonld(seo_client):
    """End-to-end: /texts/{id} response includes the JSON-LD script tag."""
    fake_index = (
        "<!doctype html><html><head>"
        "<title>佛津 FoJin</title>"
        '<meta name="description" content="generic" />'
        "</head><body></body></html>"
    )

    async def _fake_fetch():
        return fake_index

    async def _fake_get_text(_db, text_id):
        return _StubText(id=text_id)

    with (
        patch.object(seo_module, "_fetch_index_html", _fake_fetch),
        patch.object(seo_module, "get_text_by_id", _fake_get_text),
    ):
        resp = await seo_client.get("/texts/9")

    assert resp.status_code == 200
    body = resp.text
    payload = _extract_jsonld(body)
    assert payload["@type"] == "Book"
    assert payload["identifier"]["value"] == "T0251"
    assert payload["translator"]["name"] == "玄奘"
    # Title and per-text meta still injected as before.
    assert "般若波羅蜜多心經" in body
    # The script tag must come before </head> so crawlers see it during the
    # head pass (some bots stop parsing at <body>).
    head_close = body.lower().rfind("</head>")
    script_pos = body.find("application/ld+json")
    assert 0 < script_pos < head_close


@pytest.mark.anyio
async def test_jsonld_does_not_break_when_payload_contains_html_like_text(seo_client):
    """JSON-LD blob must escape `</` so crawlers don't see a fake script close."""
    fake_index = "<!doctype html><html><head><title>x</title></head><body></body></html>"

    async def _fake_fetch():
        return fake_index

    async def _fake_get_text(_db, text_id):
        return _StubText(translator="evil</script><script>alert(1)</script>")

    with (
        patch.object(seo_module, "_fetch_index_html", _fake_fetch),
        patch.object(seo_module, "get_text_by_id", _fake_get_text),
    ):
        resp = await seo_client.get("/texts/9")

    body = resp.text
    # The literal "</script>" must NOT appear before the legitimate one
    # closing our ld+json tag — otherwise we'd have a script-injection.
    ld_open = body.find("application/ld+json")
    legit_close = body.find("</script>", ld_open)
    assert legit_close > ld_open
    # And there should be exactly one </script> for our ld+json (the next
    # </script> after `application/ld+json` is the closing tag, not an
    # injected one).
    assert body.count('<script type="application/ld+json">') == 1
    # The escaped form must appear instead of the raw one in the payload.
    assert "<\\/script>" in body
