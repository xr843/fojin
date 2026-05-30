"""Read-only FRBR Work API tests.

The backend has no live Postgres in CI, so — following the established pattern
in test_smoke.py / test_source_stats.py — we override the ``get_db`` dependency
with an ``AsyncMock`` session and feed each ``execute`` call a controlled result
object via ``side_effect``. This exercises the real router logic (title-per-lang
selection, root-first ordering, witness_count, q filtering) without a DB.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #


def _make_work(**kw):
    """A fake Work ORM row."""
    w = MagicMock()
    w.id = kw.get("id", 1)
    w.slug = kw.get("slug", "lotus-sutra")
    w.title_primary = kw.get("title_primary", "妙法蓮華經")
    w.title_sa = kw.get("title_sa", "Saddharmapuṇḍarīka")
    w.title_pi = kw.get("title_pi")
    w.sc_root_uid = kw.get("sc_root_uid")
    w.toh_number = kw.get("toh_number")
    w.category = kw.get("category", "sutra")
    w.note = kw.get("note")
    w.created_at = kw.get("created_at", datetime.now(UTC))
    return w


def _make_witness(**kw):
    wit = MagicMock()
    wit.text_id = kw["text_id"]
    wit.work_id = kw.get("work_id", 1)
    wit.role = kw.get("role", "translation")
    wit.lang = kw.get("lang", "lzh")
    wit.canon = kw.get("canon")
    wit.confidence = kw.get("confidence", "auto")
    return wit


def _make_text(**kw):
    t = MagicMock()
    t.id = kw["id"]
    t.cbeta_id = kw.get("cbeta_id")
    t.title_zh = kw.get("title_zh")
    t.title_en = kw.get("title_en")
    t.title_sa = kw.get("title_sa")
    t.title_bo = kw.get("title_bo")
    t.title_pi = kw.get("title_pi")
    t.has_content = kw.get("has_content", False)
    return t


def _scalar_result(value):
    """Mock result whose ``.scalar()`` / ``.scalar_one_or_none()`` returns value."""
    r = MagicMock()
    r.scalar.return_value = value
    r.scalar_one_or_none.return_value = value
    return r


def _scalars_all_result(items):
    """Mock result whose ``.scalars().all()`` returns items."""
    r = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    r.scalars.return_value = scalars
    return r


def _all_result(rows):
    """Mock result whose ``.all()`` returns rows (list of row tuples / objects)."""
    r = MagicMock()
    r.all.return_value = rows
    return r


def _override_db(side_effect):
    """Install a mock DB session with the given execute() side_effect; returns
    a teardown callable."""
    from app.database import get_db as real_get_db
    from app.main import app

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=side_effect)
    app.dependency_overrides[real_get_db] = lambda: mock_session

    def teardown():
        app.dependency_overrides.pop(real_get_db, None)

    return teardown


# --------------------------------------------------------------------------- #
# GET /works/{slug}
# --------------------------------------------------------------------------- #


@pytest.mark.anyio
async def test_get_work_detail_with_witness_count(client):
    work = _make_work()
    # call 1: select Work by slug ; call 2: count witnesses
    teardown = _override_db([_scalar_result(work), _scalar_result(2)])
    try:
        resp = await client.get("/api/works/lotus-sutra")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["slug"] == "lotus-sutra"
        assert data["title_primary"] == "妙法蓮華經"
        assert data["title_sa"] == "Saddharmapuṇḍarīka"
        assert data["witness_count"] == 2
    finally:
        teardown()


@pytest.mark.anyio
async def test_get_work_404_for_missing_slug(client):
    teardown = _override_db([_scalar_result(None)])
    try:
        resp = await client.get("/api/works/does-not-exist")
        assert resp.status_code == 404, resp.text
    finally:
        teardown()


# --------------------------------------------------------------------------- #
# GET /works/{slug}/witnesses
# --------------------------------------------------------------------------- #


@pytest.mark.anyio
async def test_list_witnesses_enriched_root_first_and_title_per_lang(client):
    # A Pali translation witness (non-root) + a Chinese root witness.
    # DB returns them root-first already (router does ORDER BY in SQL); we feed
    # them in the router's expected order to verify enrichment + shape.
    root_wit = _make_witness(
        text_id=10, role="root", lang="lzh", canon="taisho", confidence="verified"
    )
    root_text = _make_text(
        id=10,
        cbeta_id="T0262",
        title_zh="妙法蓮華經",
        title_en="Lotus Sutra",
        has_content=True,
    )
    pi_wit = _make_witness(
        text_id=20, role="translation", lang="pi", canon="pali", confidence="auto"
    )
    pi_text = _make_text(
        id=20,
        cbeta_id=None,
        title_zh="法華經(巴利)",
        title_pi="Saddhammapuṇḍarīka",
        title_en="Lotus (Pali)",
        has_content=False,
    )

    # call 1: select Work.id by slug ; call 2: join select witnesses+texts
    rows = [(root_wit, root_text), (pi_wit, pi_text)]
    teardown = _override_db([_scalar_result(1), _all_result(rows)])
    try:
        resp = await client.get("/api/works/lotus-sutra/witnesses")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data) == 2

        # root-first ordering preserved
        assert data[0]["role"] == "root"
        assert data[0]["text_id"] == 10
        assert data[0]["cbeta_id"] == "T0262"
        # lzh witness -> title_zh
        assert data[0]["title"] == "妙法蓮華經"
        assert data[0]["lang"] == "lzh"
        assert data[0]["canon"] == "taisho"
        assert data[0]["confidence"] == "verified"
        assert data[0]["has_content"] is True

        # pi witness -> title_pi (not title_zh, not title_en)
        assert data[1]["role"] == "translation"
        assert data[1]["lang"] == "pi"
        assert data[1]["title"] == "Saddhammapuṇḍarīka"
        assert data[1]["cbeta_id"] is None
        assert data[1]["has_content"] is False
    finally:
        teardown()


@pytest.mark.anyio
async def test_list_witnesses_404_for_missing_slug(client):
    teardown = _override_db([_scalar_result(None)])
    try:
        resp = await client.get("/api/works/nope/witnesses")
        assert resp.status_code == 404, resp.text
    finally:
        teardown()


# --------------------------------------------------------------------------- #
# GET /works?q=
# --------------------------------------------------------------------------- #


@pytest.mark.anyio
async def test_list_works_finds_by_query(client):
    work = _make_work()

    # Aggregate row for the page: work_id -> (witness_count, langs)
    agg_row = MagicMock()
    agg_row.work_id = 1
    agg_row.witness_count = 2
    agg_row.langs = ["pi", "lzh"]

    # call 1: count ; call 2: select works ; call 3: aggregate
    teardown = _override_db(
        [
            _scalar_result(1),
            _scalars_all_result([work]),
            _all_result([agg_row]),
        ]
    )
    try:
        resp = await client.get("/api/works", params={"q": "法華"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total"] == 1
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["slug"] == "lotus-sutra"
        assert item["title_primary"] == "妙法蓮華經"
        assert item["witness_count"] == 2
        assert item["langs"] == ["lzh", "pi"]  # sorted
    finally:
        teardown()


@pytest.mark.anyio
async def test_list_works_empty(client):
    teardown = _override_db([_scalar_result(0), _scalars_all_result([])])
    try:
        resp = await client.get("/api/works", params={"q": "zzz-no-match"})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []
    finally:
        teardown()
