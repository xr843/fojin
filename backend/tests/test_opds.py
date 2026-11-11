"""OPDS catalogue (/api/opds) tests.

The DB is an AsyncMock whose execute() results are queued per test; SQL itself
is checked by compiling the captured statements for PostgreSQL.
"""

import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects import postgresql

from app.api.opds import ACQ_REL, PAGE_SIZE, _section_of

A = "{http://www.w3.org/2005/Atom}"


def _bt(i: int, cbeta_id: str, title: str = "金剛般若波羅蜜經"):
    return SimpleNamespace(
        id=i,
        cbeta_id=cbeta_id,
        title_zh=title,
        translator="鳩摩羅什譯",
        dynasty="姚秦",
        fascicle_count=1,
        lang="lzh",
        created_at=datetime(2026, 3, 1, tzinfo=UTC),
    )


def _scalar(v):
    r = MagicMock()
    r.scalar.return_value = v
    return r


def _scalars(rows):
    r = MagicMock()
    r.scalars.return_value.all.return_value = rows
    return r


def _all(rows):
    r = MagicMock()
    r.all.return_value = rows
    return r


def _first(v):
    r = MagicMock()
    r.first.return_value = v
    return r


@pytest_asyncio.fixture
async def opds():
    """(client, session) — session.execute.side_effect is set per test."""
    session = AsyncMock()

    async def get_db():
        yield session

    with patch("app.core.elasticsearch.init_es", new_callable=AsyncMock), patch(
        "app.core.elasticsearch.close_es", new_callable=AsyncMock
    ), patch("app.main.aioredis") as redis_mod:
        redis_mod.from_url.return_value = AsyncMock()
        from app.database import get_db as real_get_db
        from app.main import app

        app.dependency_overrides[real_get_db] = get_db
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c, session
        app.dependency_overrides.pop(real_get_db, None)


def _sql(session, call_index: int) -> str:
    stmt = session.execute.call_args_list[call_index].args[0]
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


# --- helpers -----------------------------------------------------------------

@pytest.mark.parametrize(
    "cid,section",
    [("T0001", "agama"), ("T0220a", "prajna"), ("T0235", "prajna"), ("T2008", "schools"), ("X0001", None)],
)
def test_section_of(cid, section):
    assert _section_of(cid) == section


# --- feeds -------------------------------------------------------------------

async def test_root_is_navigation_feed_with_absolute_links(opds):
    client, session = opds
    session.execute.side_effect = [_all([("T", 2390), ("X", 1230)])]
    r = await client.get("/api/opds")
    assert r.status_code == 200
    assert "kind=navigation" in r.headers["content-type"]
    feed = ET.fromstring(r.content)
    hrefs = [link.get("href") for link in feed.iter(f"{A}link")]
    assert "https://fojin.app/api/opds/taisho" in hrefs
    assert "https://fojin.app/api/opds/xuzang" in hrefs
    assert "https://fojin.app/api/opds/opensearch.xml" in hrefs
    assert all(h.startswith("https://") for h in hrefs)
    assert "2390" in r.text and "1230" in r.text


async def test_listing_is_restricted_to_allowed_redistributable_sources(opds):
    client, session = opds
    session.execute.side_effect = [_all([])]
    await client.get("/api/opds")
    sql = _sql(session, 0)
    assert "data_sources.code IN ('cbeta')" in sql
    assert "data_sources.redistribution_allowed IS true" in sql
    assert "buddhist_texts.has_content IS true" in sql


async def test_taisho_lists_only_nonempty_sections(opds):
    client, session = opds
    session.execute.side_effect = [_scalars(["T0001", "T0002", "T0235"])]
    r = await client.get("/api/opds/taisho")
    titles = [e.find(f"{A}title").text for e in ET.fromstring(r.content).iter(f"{A}entry")]
    assert titles == ["阿含部", "般若部"]


async def test_section_feed_entries_and_pagination(opds):
    client, session = opds
    books = [_bt(i, f"T{220 + i:04d}") for i in range(PAGE_SIZE)]
    session.execute.side_effect = [_scalar(PAGE_SIZE + 3), _scalars(books)]
    r = await client.get("/api/opds/taisho/prajna")
    assert r.status_code == 200
    assert "kind=acquisition" in r.headers["content-type"]
    feed = ET.fromstring(r.content)
    entries = list(feed.iter(f"{A}entry"))
    assert len(entries) == PAGE_SIZE
    links = {link.get("rel"): link for link in entries[0].iter(f"{A}link")}
    assert links[ACQ_REL].get("href") == "https://fojin.app/api/opds/download/0.epub"
    assert links[ACQ_REL].get("type") == "application/epub+zip"
    assert links["alternate"].get("href") == "https://fojin.app/texts/0"
    feed_links = {link.get("rel"): link.get("href") for link in feed.findall(f"{A}link")}
    assert feed_links["next"] == "https://fojin.app/api/opds/taisho/prajna?page=2"
    assert "previous" not in feed_links
    # section bounds reach the SQL
    sql = _sql(session, 1)
    assert "BETWEEN '0220' AND '0261'" in sql


async def test_unknown_section_and_page_out_of_range_404(opds):
    client, session = opds
    assert (await client.get("/api/opds/taisho/nope")).status_code == 404
    session.execute.side_effect = [_scalar(10)]
    assert (await client.get("/api/opds/xuzang?page=5")).status_code == 404


async def test_search_matches_traditional_form_of_simplified_query(opds):
    client, session = opds
    session.execute.side_effect = [_scalar(1), _scalars([_bt(5, "T0235")])]
    r = await client.get("/api/opds/search", params={"q": "金刚"})
    assert r.status_code == 200
    assert "金剛般若波羅蜜經" in r.text
    sql = _sql(session, 1)
    assert "金剛" in sql and "金刚" in sql


async def test_opensearch_description_points_at_search(opds):
    client, _ = opds
    r = await client.get("/api/opds/opensearch.xml")
    assert r.status_code == 200
    assert "https://fojin.app/api/opds/search?q={searchTerms}" in r.text


# --- download ----------------------------------------------------------------

async def test_download_refuses_texts_outside_catalogue(opds):
    client, session = opds
    session.execute.side_effect = [_first(None)]
    r = await client.get("/api/opds/download/999.epub")
    assert r.status_code == 404


async def test_download_serves_epub_with_rights_page(opds):
    import zipfile
    from io import BytesIO

    from app.services.text_export import ExportDoc, ExportJuan

    client, session = opds
    session.execute.side_effect = [_first((5,))]
    doc = ExportDoc(title="金剛般若波羅蜜經", cbeta_id="T0235", juans=[ExportJuan(1, ["如是我聞。"], [])], text_id=5)
    with patch("app.api.opds.build_export_doc", AsyncMock(return_value=doc)):
        r = await client.get("/api/opds/download/5.epub")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/epub+zip")
    assert 'filename="T0235.epub"' in r.headers["content-disposition"]
    names = zipfile.ZipFile(BytesIO(r.content)).namelist()
    assert "OEBPS/colophon.xhtml" in names


# --- rate limit --------------------------------------------------------------

async def test_download_prefix_shares_one_strict_window():
    from starlette.requests import Request
    from starlette.responses import PlainTextResponse

    from app.config import settings
    from app.core.rate_limit import RateLimitMiddleware

    keys: list[str] = []

    class Redis:
        async def incr(self, key):
            keys.append(key)
            return settings.rate_limit_opds_download + 1

        async def expire(self, key, ttl):
            return True

    def req(path):
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": path,
                "headers": [(b"x-forwarded-for", b"1.2.3.4")],
                "query_string": b"",
                "client": ("172.18.0.9", 1),
                "app": SimpleNamespace(state=SimpleNamespace(redis=Redis())),
            }
        )

    async def ok(_):
        return PlainTextResponse("ok")

    mw = RateLimitMiddleware(app=None)
    r1 = await mw.dispatch(req("/api/opds/download/1.epub"), ok)
    await mw.dispatch(req("/api/opds/download/2.epub"), ok)
    assert r1.status_code == 429
    assert keys[0] == keys[1]
    assert "/api/opds/download/" in keys[0]
