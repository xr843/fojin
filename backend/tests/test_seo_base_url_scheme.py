"""Regression tests for the public base URL scheme used by SEO routes.

Behind nginx, ``request.base_url`` always reports ``http`` (uvicorn runs
without ``--proxy-headers`` on purpose — see backend/entrypoint.sh). Every URL
built from it therefore went out as ``http://``: og:url, the JSON-LD ``url``,
and every breadcrumb item. Cloudflare's Automatic HTTPS Rewrites patched only
the ``href``-bearing ``<link rel="canonical">``, so production served pages
whose canonical said https while og:url and the structured data said http —
and the sitemap (hardcoded https) disagreed with both.
"""

import re

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.api.seo import public_base_url


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/probe")
    async def probe(request: Request):  # pragma: no cover - trivial
        return {"base": public_base_url(request)}

    return app


async def _probe(headers: dict[str, str] | None = None) -> str:
    transport = ASGITransport(app=_app())
    async with AsyncClient(transport=transport, base_url="http://fojin.app") as client:
        resp = await client.get("/probe", headers=headers or {})
    return resp.json()["base"]


@pytest.mark.asyncio
async def test_forwarded_proto_https_upgrades_scheme():
    assert await _probe({"X-Forwarded-Proto": "https"}) == "https://fojin.app"


@pytest.mark.asyncio
async def test_without_header_scheme_is_left_alone():
    """Self-hosters running plain HTTP must not be handed https URLs."""
    assert await _probe() == "http://fojin.app"


@pytest.mark.asyncio
async def test_forwarded_proto_http_stays_http():
    assert await _probe({"X-Forwarded-Proto": "http"}) == "http://fojin.app"


@pytest.mark.asyncio
async def test_multi_value_header_takes_first_hop():
    assert await _probe({"X-Forwarded-Proto": "https, http"}) == "https://fojin.app"


@pytest.mark.asyncio
async def test_uppercase_value_is_normalised():
    assert await _probe({"X-Forwarded-Proto": "HTTPS"}) == "https://fojin.app"


@pytest.mark.asyncio
@pytest.mark.parametrize("bogus", ["javascript", "ftp", "", "  ", "https://evil.com"])
async def test_bogus_scheme_is_ignored(bogus: str):
    """Anything that is not exactly http/https must not reach the URL."""
    assert await _probe({"X-Forwarded-Proto": bogus}) == "http://fojin.app"


@pytest.mark.asyncio
async def test_host_beginning_with_http_survives_the_rewrite():
    """A host whose name starts with "http" must come back intact.

    Note on what this does NOT prove: mutating the implementation's
    ``re.sub(..., count=1)`` into a blanket ``str.replace`` leaves this test
    green. That is not a gap in the case — a base URL is always ``scheme://host``
    and a host can never contain a second ``://``, so the two forms are
    genuinely equivalent here. ``count=1`` is kept as defence in depth for the
    day this helper is handed something with a path, not because a test pins it.
    """
    transport = ASGITransport(app=_app())
    async with AsyncClient(transport=transport, base_url="http://http-archive.example") as client:
        resp = await client.get("/probe", headers={"X-Forwarded-Proto": "https"})
    assert resp.json()["base"] == "https://http-archive.example"


@pytest.mark.asyncio
async def test_person_page_canonical_and_og_url_agree(monkeypatch):
    """End-to-end: the two signals that contradicted each other in production.

    This is the assertion that actually mattered — a page whose canonical and
    og:url disagree on scheme is a self-contradictory signal to crawlers.
    """
    from app.api import seo_persons

    class _Entity:
        id = 42
        name_zh = "法藏"
        name_en = name_sa = name_pi = name_bo = None
        entity_type = "person"
        description = "华严宗祖师"
        properties: dict = {}
        external_ids: dict = {}

    html = seo_persons._render_person_html(
        _Entity(),
        related_texts=[],
        related_persons=[],
        canonical="https://fojin.app/persons/42",
        base_url="https://fojin.app",
    )

    canonical = re.search(r'<link rel="canonical" href="([^"]+)"', html)
    og_url = re.search(r'<meta property="og:url" content="([^"]+)"', html)
    assert canonical and og_url
    assert canonical.group(1) == og_url.group(1)
    assert canonical.group(1).startswith("https://")

    # The structured data must agree too — Cloudflare never rewrites <script>.
    assert "http://fojin.app" not in html
