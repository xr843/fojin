"""游客消息日计数：UPSERT 语句、口径（失败不计）、序列补零。

背景：游客对话内容刻意不落库（隐私），管理面板每日消息数只数 chat_messages
就只覆盖注册用户。daily_metric_counts 补"数"不碰"内容"。
"""

from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.services.admin_service import _daily_metric_series
from app.services.chat import _record_anonymous_message
from app.services.daily_metrics import ANONYMOUS_MESSAGES, increment_daily_metric

pytestmark = pytest.mark.asyncio


async def test_increment_compiles_to_pg_upsert():
    """语句必须是 Postgres UPSERT（ON CONFLICT 累加）——并发游客同秒提问
    不丢数不撞主键。用 postgresql 方言编译验证，防止被改成朴素 INSERT。"""
    db = AsyncMock()
    await increment_daily_metric(db, ANONYMOUS_MESSAGES, day=date(2026, 8, 8))

    stmt = db.execute.call_args.args[0]
    from sqlalchemy.dialects import postgresql

    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "INSERT INTO daily_metric_counts" in sql
    assert "ON CONFLICT" in sql
    assert "count + " in sql  # 累加而非覆盖


def _sessionmaker_returning(db):
    @asynccontextmanager
    async def _ctx():
        yield db

    return _ctx


async def test_anonymous_success_counts_and_commits():
    db = AsyncMock()
    with patch("app.services.chat.increment_daily_metric", new=AsyncMock()) as inc:
        await _record_anonymous_message(_sessionmaker_returning(db), "诸行无常，是生灭法。")
        inc.assert_awaited_once()
        assert inc.await_args.args[1] == ANONYMOUS_MESSAGES
    db.commit.assert_awaited_once()


async def test_anonymous_failed_answer_not_counted():
    """口径对齐登录侧（_save_messages 跳过失败答案）：失败/空答不计数。"""
    db = AsyncMock()
    with patch("app.services.chat.increment_daily_metric", new=AsyncMock()) as inc:
        # 真实失败哨兵前缀之一（prompt_builder._FAILED_ANSWER_PREFIXES）
        await _record_anonymous_message(
            _sessionmaker_returning(db), "抱歉，AI 服务暂时不可用，请稍后重试。"
        )
        inc.assert_not_awaited()
    db.commit.assert_not_awaited()


async def test_count_failure_never_raises():
    """计数失败绝不能炸掉流——用户已经拿到答案了。"""
    db = AsyncMock()
    with patch(
        "app.services.chat.increment_daily_metric",
        new=AsyncMock(side_effect=RuntimeError("pg down")),
    ):
        await _record_anonymous_message(_sessionmaker_returning(db), "如是我闻。")  # 不抛即过


async def test_daily_metric_series_zero_fills():
    """缺日补零：图表的 date_grid 每天都要有点，不能有洞。"""
    d0, d1, d2 = date(2026, 8, 6), date(2026, 8, 7), date(2026, 8, 8)
    db = AsyncMock()
    db.execute.return_value.all = lambda: [(d1, 5)]

    series = await _daily_metric_series(db, ANONYMOUS_MESSAGES, [d0, d1, d2])
    # DailyCount.date 是 isoformat 字符串（与 _daily_counts 同约定）——
    # 第一版实现传了 date 对象，被这条测试当场抓出。
    assert [(s.date, s.count) for s in series] == [
        ("2026-08-06", 0),
        ("2026-08-07", 5),
        ("2026-08-08", 0),
    ]
