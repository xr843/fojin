"""Reverse-index ("appears in N sutras") lookup must not hold a pool connection
for tens of seconds. Prod outage 2026-06-23: short/uncommon CJK headwords that
the trgm index can't serve seq-scan the 406MB content table for ~60s; under
crawler load these pile up and exhaust the DB pool, making backend unhealthy.
The block is a best-effort SEO nicety — cap its statement_timeout and drop it on
timeout rather than starve the pool.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.api.seo_dict import _fetch_reverse_index, dict_seo_html


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
async def test_skips_two_char_headwords_the_trgm_index_cannot_serve():
    """A 2-char headword can NEVER be served by the trgm index, so running it
    is pure waste — it always burns the full timeout budget and returns nothing.

    pg_trgm can only use the index for a ``LIKE '%x%'`` pattern when the pattern
    contains at least one *complete* trigram, i.e. 3+ characters. An unanchored
    2-char pattern yields zero extractable trigrams, so the planner falls back to
    a Seq Scan over ``text_contents`` — 276MB of TOASTed content that must be
    detoasted and ILIKE-rechecked row by row.

    Measured on prod (2026-07-21), 8 random 2-char headwords: 11.8s / 13.5s /
    14.0s / 14.8s and 4 more that did not finish within 20s — against a 3s
    budget. Success rate is therefore 0%: every such lookup times out, rolls
    back, and renders the page without the block. It also touches ~795MB of
    shared buffers (shared_buffers is 640MB), flushing the cache that the
    *fast* 3+-char lookups depend on — which is why they time out too.

    So this is not a tradeoff: skipping 2-char lookups loses no functionality
    that exists today, and stops the collateral damage.
    """
    db = AsyncMock()
    assert await _fetch_reverse_index(db, "般若") == []
    assert await _fetch_reverse_index(db, "菩提") == []
    db.execute.assert_not_awaited()


@pytest.mark.anyio
async def test_caps_statement_timeout_before_the_ilike():
    db = AsyncMock()
    res = MagicMock()
    res.all.return_value = []
    db.execute.return_value = res

    # 3+ chars: the trgm index can serve this, so it is allowed through to the DB.
    await _fetch_reverse_index(db, "波羅蜜")

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

    out = await _fetch_reverse_index(db, "波羅蜜")
    assert out == []
    db.rollback.assert_awaited()  # aborted txn cleaned so the session is reusable


@pytest.mark.anyio
async def test_dict_page_survives_reverse_index_rollback():
    """Live /dict/般若 and /dict/菩提 returned 500 (2026-06-24): those two common
    terms make the reverse-index ILIKE time out, which rolls back the session
    (the #801 best-effort guard) — and the rollback EXPIRES the joinedload'd
    entries loaded earlier. Rendering then touched ``e.source.name_zh`` /
    ``e.definition`` on the now-expired async ORM rows, triggering a lazy reload
    → MissingGreenlet → 500. This is the #654/#763 detached-row trap, 3rd time.

    The page MUST render from a primitive snapshot taken BEFORE the reverse-index
    lookup, so a mid-request rollback can never 500 the page.
    """

    class _ExpiringEntry:
        """An ORM row that raises on attribute access once the session is rolled
        back — exactly how async SQLAlchemy behaves on an expired attribute."""

        def __init__(self):
            self.expired = False

        def _guard(self):
            if self.expired:
                raise RuntimeError(
                    "greenlet_spawn has not been called; can't reload expired "
                    "attribute (MissingGreenlet after rollback)"
                )

        @property
        def definition(self):
            self._guard()
            return "般若：智慧；超越世俗分别的洞见。"

        @property
        def reading(self):
            self._guard()
            return None

        @property
        def source(self):
            self._guard()
            return SimpleNamespace(name_zh="佛光大辞典")

    entry = _ExpiringEntry()

    db = AsyncMock()
    entries_result = MagicMock()
    entries_result.unique.return_value.scalars.return_value.all.return_value = [entry]
    db.execute.return_value = entries_result

    async def _fake_reverse(_db, _headword):
        # Simulate the timeout path: the session was rolled back, so every
        # previously-loaded ORM row is now expired.
        entry.expired = True
        return []

    request = MagicMock()
    request.base_url = "http://test/"

    # 般若 is identical in simplified/traditional, so the variant probe is
    # skipped and the only pre-render DB call is the entries SELECT (mocked).
    with patch("app.api.seo_dict._fetch_reverse_index", _fake_reverse):
        resp = await dict_seo_html("般若", request, db)

    assert resp.status_code == 200
    body = resp.body.decode()
    assert "般若" in body
    # The source name was snapshotted before the rollback, so it still renders.
    assert "佛光大辞典" in body
