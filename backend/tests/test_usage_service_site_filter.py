"""后台「模块使用」的统计口径。

同一个 Umami 实例还托管别的站（2026-11-24 实测：7 天里昆虫站事件 11,082 条，占看板 73%），
站长自己的测试也会混进来（trace_done 72 次里 49 次是站长）。这里截下真正发给 Umami 库的
每条 SQL，确认按 fojin 域名限定站点、排除站长与本机开发，并把人数带回给前端。
"""

import asyncio
from typing import ClassVar
from unittest.mock import patch

from app.config import settings
from app.services import usage_service


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    calls: ClassVar[list[tuple[str, dict]]] = []
    event_rows: ClassVar[list[tuple]] = []

    def __init__(self, _engine):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, params):
        _FakeSession.calls.append((str(stmt), dict(params)))
        # 第一条是事件统计，第二条是检索词
        return _Result(_FakeSession.event_rows if len(_FakeSession.calls) == 1 else [])


def _run(event_rows):
    _FakeSession.calls = []
    _FakeSession.event_rows = event_rows
    with (
        patch.object(usage_service, "_get_engine", return_value=object()),
        patch.object(usage_service, "AsyncSession", _FakeSession),
    ):
        return asyncio.run(usage_service._query_module_usage(7))


def test_every_umami_query_is_scoped_to_fojin_site_and_drops_staff():
    _run([])
    assert len(_FakeSession.calls) == 2
    for sql, params in _FakeSession.calls:
        assert "FROM website WHERE domain = :domain" in sql, sql
        assert "url_path LIKE '/admin%'" in sql, sql
        assert "'localhost'" in sql, sql
        assert params["domain"] == settings.umami_site_domain == "fojin.app"
    # 检索词也只算非站长
    assert "NOT ev.is_staff" in _FakeSession.calls[1][0]


def test_users_and_excluded_staff_are_reported():
    # (event_name, 非站长次数, 非站长人数, 站长次数)
    out = _run([("chat", 10, 4, 1), ("trace_done", 3, 2, 49), ("trace_error", 0, 0, 2)])
    by_name = {e["event_name"]: e for e in out["events"]}
    assert by_name["chat"]["users"] == 4
    assert by_name["trace_done"] == {"event_name": "trace_done", "label": "trace_done", "count": 3, "users": 2}
    # 只有站长触发过的事件不出现在看板上
    assert "trace_error" not in by_name
    assert out["excluded_staff_events"] == 52
    assert out["answer_quality"]["chat_questions"] == 10
