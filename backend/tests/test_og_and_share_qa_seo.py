"""Tests for the dynamic OG card endpoint and share-Q&A SSR meta injection.

Covers:
- /api/og/share/qa/{id} returns a PNG for an existing SharedQA row
- /api/og/share/qa/{id} 404s on unknown id
- /share/qa/{id} HTML contains per-question og:* / twitter:card and a
  canonical pointing back to itself, instead of inheriting the
  homepage defaults.
- /share/qa/{id} 404s on unknown id
- The og:image URL points at /api/og/share/qa/{id} so crawlers can fetch it.
"""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api import seo as seo_module


class _StubSharedQA:
    """Minimal stand-in for app.models.chat.SharedQA used in tests."""

    def __init__(
        self,
        *,
        share_id: str = "abc123",
        question: str = "什么是空？",
        answer: str = "**空** 是 *缘起性空* 的核心 [link](http://x). 【《心经》第1卷】 详细解释 …",
        sources=None,
    ):
        self.id = share_id
        self.question = question
        self.answer = answer
        self.sources = sources or [{"title_zh": "般若波羅蜜多心經", "cbeta_id": "T0251"}]


def _patch_db(scalar_returns):
    """Override the FastAPI get_db dep so SharedQA queries return our stub.

    ``scalar_returns`` is the value the mocked ``db.scalar(...)`` will
    return for every call within the test.
    """
    from app.database import get_db
    from app.main import app

    async def fake_get_db():
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=scalar_returns)
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()
        yield mock_db

    app.dependency_overrides[get_db] = fake_get_db


def _restore_db():
    from app.database import get_db
    from app.main import app

    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def og_client():
    """A bare async client without the ES/Redis fixtures (those aren't needed
    for the og + seo routes)."""
    with (
        patch("app.core.elasticsearch.init_es", new_callable=AsyncMock),
        patch("app.core.elasticsearch.close_es", new_callable=AsyncMock),
        patch("app.main.aioredis") as mock_redis_mod,
    ):
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_redis_mod.from_url.return_value = mock_redis

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest.mark.anyio
async def test_og_image_endpoint_returns_png(og_client):
    """Existing SharedQA → 200 with image/png body."""
    _patch_db(_StubSharedQA())
    try:
        resp = await og_client.get("/api/og/share/qa/abc123")
    finally:
        _restore_db()

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    # Must include the 24h CDN cache directive.
    assert "max-age=86400" in resp.headers["cache-control"]
    # PNG magic bytes — proves we actually rendered an image and not an error page.
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"
    # Reasonable size for a 1200×630 mostly-white PNG with a few text blocks.
    assert 2000 < len(resp.content) < 200_000


@pytest.mark.anyio
async def test_og_image_404_when_share_missing(og_client):
    """Missing SharedQA → 404 (not a broken PNG)."""
    _patch_db(None)
    try:
        resp = await og_client.get("/api/og/share/qa/does-not-exist")
    finally:
        _restore_db()

    assert resp.status_code == 404


@pytest.mark.anyio
async def test_share_qa_seo_html_injects_per_question_meta(og_client):
    """/share/qa/{id} HTML must carry per-question title / og:* / canonical."""
    _patch_db(_StubSharedQA(question="第二次结集为何分裂？"))

    fake_index = (
        "<!doctype html><html><head>"
        "<title>佛津 FoJin</title>"
        '<meta name="description" content="生 generic" />'
        '<meta property="og:image" content="/landscape-bg.png" />'
        "</head><body></body></html>"
    )

    async def _fake_fetch():
        return fake_index

    try:
        with patch.object(seo_module, "_fetch_index_html", _fake_fetch):
            resp = await og_client.get("/share/qa/abc123")
    finally:
        _restore_db()

    assert resp.status_code == 200
    body = resp.text

    # Title now reflects the question, not the homepage.
    assert "<title>第二次结集为何分裂？" in body

    # Per-question og:* tags present.
    assert 'property="og:title"' in body
    assert "第二次结集为何分裂？" in body
    assert 'property="og:image"' in body
    # og:image points at the dynamic card endpoint, not the static landscape.
    assert "/api/og/share/qa/abc123" in body
    assert "/landscape-bg.png" not in body  # legacy static image was stripped

    # twitter:card and canonical pointing back to ourselves.
    assert 'name="twitter:card"' in body and "summary_large_image" in body
    assert 'rel="canonical"' in body
    assert "/share/qa/abc123" in body

    # Markdown was stripped from the description (no leading **).
    assert "**空**" not in body
    # Citation pills (【…】) and inline link markup gone.
    assert "【《心经》第1卷】" not in body


@pytest.mark.anyio
async def test_share_qa_seo_html_404_when_share_missing(og_client):
    """/share/qa/{id} returns 404 when the row doesn't exist."""
    _patch_db(None)
    try:
        resp = await og_client.get("/share/qa/no-such-id")
    finally:
        _restore_db()

    assert resp.status_code == 404


@pytest.mark.anyio
async def test_share_qa_seo_falls_back_when_frontend_unreachable(og_client):
    """If frontend nginx is down, we still return readable HTML for crawlers."""
    import httpx

    _patch_db(_StubSharedQA(question="缘起是什么？"))

    async def _explode():
        raise httpx.HTTPError("frontend down")

    try:
        with patch.object(seo_module, "_fetch_index_html", _explode):
            resp = await og_client.get("/share/qa/abc123")
    finally:
        _restore_db()

    assert resp.status_code == 200
    body = resp.text
    # Fallback HTML still carries the per-question og: tags.
    assert "缘起是什么？" in body
    assert 'property="og:image"' in body
    assert "/api/og/share/qa/abc123" in body
