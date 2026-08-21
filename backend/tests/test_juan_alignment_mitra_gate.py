"""阅读器「多语对读」面板也要过 MITRA 质量门。

`services/mitra_gate` 的 docstring 列了两条历史上绕过门禁、后来接上的路径
（引用抽屉、覆盖率目录）。`get_juan_alignment` 是第三条，一直没接上——而它正是
ParallelReaderPage / ReaderParallelPanel 在用的端点。后果有两面：

1. 面板会把某个段落标成「有平行段」，靠的却是引用抽屉和 RAG 上下文都拒绝展示的
   行；用户点开可能得到空的。
2. 低分平行段直接展示给读者。

2026-08-21 在生产库上实测这个改动：text 2 / juan 14，块列表 25 → 25（不变，
因为每块都还有通过的行），批量取回 432 → 396 行——36 条低分平行段被扣下。

⚠️ 影响面要说实话：全库 908,620 行里 903,620 行（99.4%）的 mitra_e_score 还没
回填，而门禁按设计对 NULL 放行，所以今天它实际只挡住 375 行。这是一致性修复，
不是用户可见的大漏；它会随着回填推进自动生效，正如门禁自己的 docstring 所说。

这里断言的是**生成的 SQL**（后端测试没有真库往返，跑通不等于 SQL 对），并且
特意验一条推理：门禁必须落在窗口函数**内部**。放到外面的话，每块 50 条的预算
会先被低分行吃掉，一个有 50 条低分行的段落会返回空，而它通过的行排在第 51 位。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.alignment import get_juan_alignment


# 打在 app.services.mitra_gate.settings 上，不是 app.config.settings：mitra_gate
# 用的是 `from app.config import settings`，它握着自己那份引用。全量跑时若有别的
# 测试重绑过 app.config.settings，补丁就会打空——这条 gate-off 用例单独跑绿、
# 全量跑红，正是这么来的。要打就打真正被读到的那个对象。


def _fake_db(captured: list):
    """A session that records every SQL it is handed and returns one chunk."""

    def _result_for(sql: str):
        res = MagicMock()
        if "COUNT(*)" in sql:
            res.fetchone.return_value = (3,)
            res.fetchall.return_value = []
        elif "SELECT DISTINCT te.chunk_index" in sql:
            # One aligned chunk, so the function does not early-return before
            # building the batched MITRA query — the second thing under test.
            res.fetchall.return_value = [(0, "如是我聞")]
            res.fetchone.return_value = None
        else:
            res.fetchall.return_value = []
            res.fetchone.return_value = None
        return res

    async def execute(stmt, params=None):
        sql = str(stmt)
        captured.append((sql, params or {}))
        return _result_for(sql)

    db = MagicMock()
    db.execute = AsyncMock(side_effect=execute)
    return db


def _sql_with(captured, *needles: str) -> tuple[str, dict]:
    """The pairs query also uses ROW_NUMBER, so callers pass every needle they
    need and all of them must match — one is not enough to identify a query."""
    for sql, params in captured:
        if all(n in sql for n in needles):
            return sql, params
    raise AssertionError(f"no captured SQL contained all of {needles!r}")


@pytest.mark.asyncio
async def test_chunk_listing_applies_the_gate(monkeypatch):
    monkeypatch.setattr("app.services.mitra_gate.settings.enable_mitra_score_gate", True)
    monkeypatch.setattr("app.services.mitra_gate.settings.mitra_min_score", 0.30)
    captured: list = []

    await get_juan_alignment(text_id=2, juan_num=14, db=_fake_db(captured))

    sql, params = _sql_with(captured, "SELECT DISTINCT te.chunk_index")
    assert "ma.mitra_e_score" in sql
    assert params.get("min_score") == 0.30


@pytest.mark.asyncio
async def test_batched_fetch_gates_inside_the_window(monkeypatch):
    monkeypatch.setattr("app.services.mitra_gate.settings.enable_mitra_score_gate", True)
    monkeypatch.setattr("app.services.mitra_gate.settings.mitra_min_score", 0.30)
    captured: list = []

    await get_juan_alignment(text_id=2, juan_num=14, db=_fake_db(captured))

    sql, params = _sql_with(captured, "ROW_NUMBER() OVER", "FROM mitra_alignments")
    assert "mitra_e_score" in sql
    assert params.get("min_score") == 0.30
    # The gate must sit inside the subquery that ROW_NUMBER partitions, i.e.
    # before the inner query closes. Filtering after the window would spend the
    # per-chunk budget on rows that then get dropped.
    inner = sql.split(") t")[0]
    assert "mitra_e_score" in inner, "gate landed outside the window function"


@pytest.mark.asyncio
async def test_gate_off_emits_no_predicate(monkeypatch):
    monkeypatch.setattr("app.services.mitra_gate.settings.enable_mitra_score_gate", False)
    captured: list = []

    await get_juan_alignment(text_id=2, juan_num=14, db=_fake_db(captured))

    for sql, params in captured:
        assert "mitra_e_score" not in sql
        assert "min_score" not in params
