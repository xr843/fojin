"""后台「模块使用」只能统计 fojin 自己的站点。

同一个 Umami 实例还托管别的站（2026-11-24 实测：7 天里昆虫站事件 11,082 条，占看板 73%，
species_switch / lesson_step 排在最前）。这里截下真正发给 Umami 库的每条 SQL，
确认都按 fojin 的域名限定了站点。
"""

import asyncio
from typing import ClassVar
from unittest.mock import patch

from app.config import settings
from app.services import usage_service


class _Result:
    def all(self):
        return []


class _FakeSession:
    calls: ClassVar[list[tuple[str, dict]]] = []

    def __init__(self, _engine):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, params):
        _FakeSession.calls.append((str(stmt), dict(params)))
        return _Result()


def test_every_umami_query_is_scoped_to_fojin_site():
    _FakeSession.calls = []
    with (
        patch.object(usage_service, "_get_engine", return_value=object()),
        patch.object(usage_service, "AsyncSession", _FakeSession),
    ):
        asyncio.run(usage_service._query_module_usage(7))

    assert len(_FakeSession.calls) == 2
    for sql, params in _FakeSession.calls:
        assert "FROM website WHERE domain = :domain" in sql, sql
        assert params["domain"] == settings.umami_site_domain == "fojin.app"
