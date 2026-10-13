"""「出现于哪些经典」反查（/dict/<词> 页面上的 best-effort 区块）。

2026-10 起走 Elasticsearch 短语查询，不再在 Postgres 里 ILIKE 全表扫：爬虫逐个枚举
约 55 万词头（KeenableBot 7 天 ~20.8 万个不同页面），每个请求都是新词，缓存无用；
旧的 ILIKE 每次 0.2–3s，让 PG 与后端常年接近 100% CPU。生产实测 ES 27–67ms，
且因索引时接上了 CBETA 硬换行，跨行的词也能找到（旧 ILIKE 漏掉的）。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.seo_dict import _fetch_reverse_index, dict_seo_html


def _fake_es(hits=None, exc=None):
    """A get_es() double: es.options(...).search(...) returns ``hits`` or raises ``exc``."""
    search = AsyncMock()
    if exc is not None:
        search.side_effect = exc
    else:
        search.return_value = {"hits": {"hits": hits or []}}
    es = MagicMock()
    es.options.return_value = SimpleNamespace(search=search)
    return es, search


@pytest.mark.anyio
async def test_skips_single_char_and_overlong_headwords():
    # 单字「出现于 N 部经」毫无意义；超长是垃圾输入。都不该发查询。
    es, search = _fake_es()
    with patch("app.api.seo_dict.get_es", return_value=es):
        assert await _fetch_reverse_index(AsyncMock(), "火") == []
        assert await _fetch_reverse_index(AsyncMock(), "字" * 201) == []
    search.assert_not_awaited()


@pytest.mark.anyio
async def test_two_char_headwords_are_now_looked_up():
    """旧做法因 pg_trgm 无法服务两字模式而整类跳过（般若、菩提从不显示这一块）；
    ES 二元组索引对两字词正好是一个 token，便宜且准确。"""
    es, search = _fake_es(hits=[{"_source": {"text_id": 9, "title_zh": "般若波羅蜜多心經", "cbeta_id": "T0251"}}])
    with patch("app.api.seo_dict.get_es", return_value=es):
        out = await _fetch_reverse_index(AsyncMock(), "般若")
    assert out == [{"id": 9, "title_zh": "般若波羅蜜多心經", "cbeta_id": "T0251"}]
    search.assert_awaited_once()


@pytest.mark.anyio
async def test_never_touches_postgres():
    """整个修复的要点：反查不得再在数据库里跑（那正是被爬虫打满的地方）。"""
    db = AsyncMock()
    es, _ = _fake_es()
    with patch("app.api.seo_dict.get_es", return_value=es):
        await _fetch_reverse_index(db, "波羅蜜")
    db.execute.assert_not_awaited()


@pytest.mark.anyio
async def test_query_is_a_phrase_one_hit_per_text_lowest_id_first():
    es, search = _fake_es()
    with patch("app.api.seo_dict.get_es", return_value=es):
        await _fetch_reverse_index(AsyncMock(), "波羅蜜")
    body = search.await_args.kwargs["body"]
    assert body["query"] == {"match_phrase": {"content": "波羅蜜"}}
    assert body["collapse"] == {"field": "text_id"}
    assert body["sort"] == [{"text_id": "asc"}]
    assert body["size"] == 8
    # 请求必须带超时：ES 慢的时候宁可不显示这一块，也不能拖住页面。
    assert es.options.call_args.kwargs["request_timeout"] <= 2.0


@pytest.mark.anyio
async def test_es_failure_drops_the_block_instead_of_raising():
    es, _ = _fake_es(exc=ConnectionError("es down"))
    with patch("app.api.seo_dict.get_es", return_value=es):
        assert await _fetch_reverse_index(AsyncMock(), "波羅蜜") == []


@pytest.mark.anyio
async def test_malformed_hits_are_skipped():
    es, _ = _fake_es(hits=[{"_source": {"text_id": "x"}}, {"_source": {}}, {"_source": {"text_id": 3, "title_zh": " 長阿含經 "}}])
    with patch("app.api.seo_dict.get_es", return_value=es):
        out = await _fetch_reverse_index(AsyncMock(), "波羅蜜")
    assert out == [{"id": 3, "title_zh": "長阿含經", "cbeta_id": ""}]


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
