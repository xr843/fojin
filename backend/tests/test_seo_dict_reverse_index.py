"""Reverse-index ("appears in N sutras") lookup must not hold a pool connection
for tens of seconds. Prod outage 2026-06-23: short/uncommon CJK headwords that
the trgm index can't serve seq-scan the 406MB content table for ~60s; under
crawler load these pile up and exhaust the DB pool, making backend unhealthy.
The block is a best-effort SEO nicety — cap its statement_timeout and drop it on
timeout rather than starve the pool.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.api.seo_dict import _fetch_reverse_index


@pytest.mark.anyio
async def test_skips_single_char_and_overlong_headwords():
    # Single-char "appears in N sutras" is meaningless (matches ~everything) and
    # is the worst case for the trgm index; overlong is junk. Neither should hit
    # the DB at all.
    db = AsyncMock()
    assert await _fetch_reverse_index(db, "火") == []
    assert await _fetch_reverse_index(db, "字" * 201) == []
    db.execute.assert_not_awaited()


@pytest.mark.anyio
async def test_caps_statement_timeout_before_the_ilike():
    db = AsyncMock()
    res = MagicMock()
    res.all.return_value = []
    db.execute.return_value = res

    await _fetch_reverse_index(db, "般若")

    first_sql = str(db.execute.await_args_list[0].args[0]).lower()
    assert "statement_timeout" in first_sql, (
        "must cap per-query statement_timeout BEFORE the ILIKE, so a slow "
        "reverse-index lookup fails fast instead of holding a pool connection "
        "~60s under crawler load"
    )


@pytest.mark.anyio
async def test_best_effort_empty_and_rollback_on_db_error():
    db = AsyncMock()
    calls = {"n": 0}

    async def _exec(*a, **k):
        calls["n"] += 1
        if calls["n"] >= 2:  # the SELECT, after the SET LOCAL statement_timeout
            raise SQLAlchemyError("canceling statement due to statement timeout")
        return MagicMock()

    db.execute.side_effect = _exec

    out = await _fetch_reverse_index(db, "般若")
    assert out == []
    db.rollback.assert_awaited()  # aborted txn cleaned so the session is reusable
