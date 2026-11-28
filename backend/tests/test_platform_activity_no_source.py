"""平台动态「无引文率」的分子要认 JSON null。

chat_messages.sources 是 SQLAlchemy JSON 列：写入 None 存成 JSON 的 null，不是 SQL NULL。
只判 IS NULL 时看板从上线起一直是 0.0%（2026-11-28 实测：6 月起每月 7–100 条无引文回答）。
"""

import asyncio

from sqlalchemy.dialects import postgresql

from app.services import stats_service


class _Result:
    def scalar(self):
        return 0

    def scalar_one_or_none(self):
        return None

    def all(self):
        return []

    def first(self):
        return None

    def scalars(self):
        return self


class _FakeDB:
    def __init__(self):
        self.sql: list[str] = []

    async def execute(self, stmt, *_a, **_k):
        self.sql.append(str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})))
        return _Result()


def test_no_source_count_matches_json_null_and_empty_list():
    db = _FakeDB()
    asyncio.run(stats_service.get_platform_activity(db, None, 7))
    no_source = [s for s in db.sql if "chat_messages.sources" in s and "assistant" in s]
    assert no_source, db.sql
    sql = no_source[0]
    assert "IS NULL" in sql
    assert "'null'" in sql and "'[]'" in sql, sql
