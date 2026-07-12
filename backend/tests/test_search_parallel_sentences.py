"""Tests for cross-lingual parallel-sentence search (MITRA).

Two layers, mirroring the repo's established patterns:

* service-level (``search_parallel_sentences``) with a mock DB fed canned rows
  — the ``_make_db_with_rows`` shape from test_rag_mitra_parallels — asserts
  dedup / NULL-score-permissiveness / shape / lang-filter / ranking SQL.
* endpoint-level (``/api/search/parallel-sentences``) with the shared ``client``
  fixture patching the service — the shape/validation pattern from
  test_semantic_search.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.search import search_parallel_sentences

# Column order returned by the service's SELECT (see search_parallel_sentences):
# zh_text, foreign_text, foreign_lang, taisho_id, text_id, juan_num,
# mitra_e_score, source, license, title
_COLS = (
    "zh_text", "foreign_text", "foreign_lang", "taisho_id", "text_id",
    "juan_num", "mitra_e_score", "source", "license", "title",
)


def _row(**over) -> tuple:
    base = {
        "zh_text": "色即是空",
        "foreign_text": "rūpaṃ śūnyatā",
        "foreign_lang": "sa",
        "taisho_id": "T0251",
        "text_id": 42,
        "juan_num": 1,
        "mitra_e_score": 0.8,
        "source": "mitra-parallel",
        "license": "CC-BY-SA-4.0",
        "title": "般若波羅蜜多心經",
    }
    base.update(over)
    return tuple(base[c] for c in _COLS)


def _make_db_with_rows(rows):
    db = MagicMock()
    result = MagicMock()
    result.fetchall.return_value = rows
    db.execute = AsyncMock(return_value=result)
    db.rollback = AsyncMock()
    return db


# ── service: short-circuit ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_blank_query_short_circuits_no_db():
    db = _make_db_with_rows([])
    out = await search_parallel_sentences(db, "   ", "all", 20)
    assert out == []
    assert db.execute.await_count == 0, "blank query must not hit the DB"


# ── service: shape ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_returns_aligned_pair_shape():
    db = _make_db_with_rows([_row()])
    out = await search_parallel_sentences(db, "色即是空", "all", 20)

    assert len(out) == 1
    hit = out[0]
    assert hit == {
        "zh_text": "色即是空",
        "foreign_text": "rūpaṃ śūnyatā",
        "foreign_lang": "sa",
        "taisho_id": "T0251",
        "text_id": 42,
        "title": "般若波羅蜜多心經",
        "juan_num": 1,
        "mitra_e_score": 0.8,
        "source": "mitra-parallel",
        "license": "CC-BY-SA-4.0",
    }


# ── service: NULL-score permissive ────────────────────────────────────


@pytest.mark.asyncio
async def test_null_mitra_e_score_rows_are_returned():
    """Unscored rows (mitra_e_score IS NULL) must still be returned — the
    ranking is NULL-permissive, mirroring _attach_mitra_parallels."""
    rows = [
        _row(foreign_text="scored", mitra_e_score=0.9),
        _row(foreign_text="unscored", mitra_e_score=None),
    ]
    db = _make_db_with_rows(rows)
    out = await search_parallel_sentences(db, "色即是空", "all", 20)

    assert len(out) == 2
    by_text = {h["foreign_text"]: h for h in out}
    assert by_text["unscored"]["mitra_e_score"] is None
    assert by_text["scored"]["mitra_e_score"] == 0.9


@pytest.mark.asyncio
async def test_null_permissive_ordering_has_no_score_gate_in_sql():
    """The SQL orders mitra_e_score DESC NULLS LAST and applies NO
    ``mitra_e_score >= x`` predicate, so unscored rows flow through."""
    db = _make_db_with_rows([_row()])
    await search_parallel_sentences(db, "色即是空", "all", 20)

    sql = str(db.execute.await_args.args[0]).lower()
    assert "nulls last" in sql
    assert "mitra_e_score >=" not in sql
    assert ">= :min_score" not in sql
    # Ranking design: match quality (similarity) first, then score, then id.
    assert "similarity(" in sql
    assert "order by" in sql


# ── service: dedup ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dedups_near_identical_foreign_sentences():
    """Near-identical foreign sentences (whitespace/case variants) collapse to
    one; the first (highest-ranked by the SQL order) copy wins."""
    rows = [
        _row(foreign_text="rūpaṃ śūnyatā", mitra_e_score=0.9),
        _row(foreign_text="Rūpaṃ  Śūnyatā", mitra_e_score=0.5),  # same, spacing/case
        _row(foreign_text="prajñā pāramitā", mitra_e_score=0.4),
    ]
    db = _make_db_with_rows(rows)
    out = await search_parallel_sentences(db, "色即是空", "all", 20)

    assert len(out) == 2
    assert out[0]["foreign_text"] == "rūpaṃ śūnyatā"  # first copy kept
    assert out[1]["foreign_text"] == "prajñā pāramitā"


@pytest.mark.asyncio
async def test_same_text_different_lang_not_deduped():
    """Dedup is per (lang, normalized text): identical romanization under a
    different foreign_lang is a distinct pair."""
    rows = [
        _row(foreign_text="dup", foreign_lang="sa"),
        _row(foreign_text="dup", foreign_lang="bo"),
    ]
    db = _make_db_with_rows(rows)
    out = await search_parallel_sentences(db, "色即是空", "all", 20)
    assert len(out) == 2


@pytest.mark.asyncio
async def test_empty_foreign_text_skipped():
    rows = [_row(foreign_text=""), _row(foreign_text="rūpaṃ")]
    db = _make_db_with_rows(rows)
    out = await search_parallel_sentences(db, "色即是空", "all", 20)
    assert [h["foreign_text"] for h in out] == ["rūpaṃ"]


# ── service: limit ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_limit_caps_returned_rows():
    rows = [_row(foreign_text=f"s{i}") for i in range(10)]
    db = _make_db_with_rows(rows)
    out = await search_parallel_sentences(db, "色即是空", "all", 3)
    assert len(out) == 3


# ── service: lang filter ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lang_filter_applied_for_sa():
    db = _make_db_with_rows([_row()])
    await search_parallel_sentences(db, "色即是空", "sa", 20)

    sql = str(db.execute.await_args.args[0])
    params = db.execute.await_args.args[1]
    assert "foreign_lang = :lang" in sql
    assert params["lang"] == "sa"


@pytest.mark.asyncio
async def test_lang_filter_applied_for_bo():
    db = _make_db_with_rows([_row(foreign_lang="bo")])
    await search_parallel_sentences(db, "色即是空", "bo", 20)

    sql = str(db.execute.await_args.args[0])
    params = db.execute.await_args.args[1]
    assert "foreign_lang = :lang" in sql
    assert params["lang"] == "bo"


@pytest.mark.asyncio
async def test_lang_all_applies_no_lang_filter():
    db = _make_db_with_rows([_row()])
    await search_parallel_sentences(db, "色即是空", "all", 20)

    sql = str(db.execute.await_args.args[0])
    params = db.execute.await_args.args[1]
    assert "foreign_lang = :lang" not in sql
    assert "lang" not in params


@pytest.mark.asyncio
async def test_unknown_lang_treated_as_all():
    db = _make_db_with_rows([_row()])
    await search_parallel_sentences(db, "色即是空", "fr", 20)

    sql = str(db.execute.await_args.args[0])
    assert "foreign_lang = :lang" not in sql


# ── service: like-metachar escaping + scan cap ────────────────────────


@pytest.mark.asyncio
async def test_like_metacharacters_escaped_in_pattern():
    db = _make_db_with_rows([])
    await search_parallel_sentences(db, "50%_off", "all", 20)

    params = db.execute.await_args.args[1]
    # % and _ are escaped so they match literally, wrapped in surrounding %…%.
    assert params["pattern"] == "%50\\%\\_off%"


@pytest.mark.asyncio
async def test_scan_cap_bounds_the_query():
    db = _make_db_with_rows([_row()])
    await search_parallel_sentences(db, "空", "all", 20)
    params = db.execute.await_args.args[1]
    assert params["scan_cap"] == 500


# ── service: DB error is swallowed ────────────────────────────────────


@pytest.mark.asyncio
async def test_db_error_returns_empty_and_rolls_back():
    db = MagicMock()
    db.execute = AsyncMock(side_effect=RuntimeError("boom"))
    db.rollback = AsyncMock()
    out = await search_parallel_sentences(db, "色即是空", "all", 20)
    assert out == []
    db.rollback.assert_awaited_once()


# ── endpoint: shape + validation ──────────────────────────────────────


@pytest.mark.anyio
async def test_endpoint_returns_pairs(client):
    canned = [{
        "zh_text": "色即是空",
        "foreign_text": "rūpaṃ śūnyatā",
        "foreign_lang": "sa",
        "taisho_id": "T0251",
        "text_id": 42,
        "title": "般若波羅蜜多心經",
        "juan_num": 1,
        "mitra_e_score": 0.8,
        "source": "mitra-parallel",
        "license": "CC-BY-SA-4.0",
    }]
    with patch(
        "app.api.search.search_parallel_sentences",
        new_callable=AsyncMock,
        return_value=canned,
    ):
        resp = await client.get("/api/search/parallel-sentences", params={"q": "色即是空"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    hit = data["results"][0]
    assert hit["foreign_text"] == "rūpaṃ śūnyatā"
    assert hit["foreign_lang"] == "sa"
    assert hit["title"] == "般若波羅蜜多心經"
    assert hit["license"] == "CC-BY-SA-4.0"


@pytest.mark.anyio
async def test_endpoint_empty_result(client):
    with patch(
        "app.api.search.search_parallel_sentences",
        new_callable=AsyncMock,
        return_value=[],
    ):
        resp = await client.get("/api/search/parallel-sentences", params={"q": "无匹配"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["results"] == []


@pytest.mark.anyio
async def test_endpoint_passes_lang_and_limit(client):
    with patch(
        "app.api.search.search_parallel_sentences",
        new_callable=AsyncMock,
        return_value=[],
    ) as mock_fn:
        resp = await client.get(
            "/api/search/parallel-sentences",
            params={"q": "空", "lang": "bo", "limit": 5},
        )

    assert resp.status_code == 200
    mock_fn.assert_awaited_once()
    # search_parallel_sentences(db, q, lang, limit) — positional after db.
    args = mock_fn.await_args.args
    assert args[1] == "空"
    assert args[2] == "bo"
    assert args[3] == 5


@pytest.mark.anyio
async def test_endpoint_limit_too_large_422(client):
    resp = await client.get(
        "/api/search/parallel-sentences", params={"q": "空", "limit": 100}
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_endpoint_limit_zero_422(client):
    resp = await client.get(
        "/api/search/parallel-sentences", params={"q": "空", "limit": 0}
    )
    assert resp.status_code == 422
