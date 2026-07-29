"""引用健康度回放的三项计数口径。

这三个数各自回答一个具体问题，口径错了就会把决策带偏，所以每一项的分子分母
都在这里钉住：

* 卷号准确率 —— 带引号的引文是否真的在所标的那一卷里。
* 引号覆盖率 —— 多少引用带「」；不带的完全无法核验（2026-07-29 实测占 51.6%）。
* 定位与标注一致率 —— 为「能否让护栏按引文自动纠正卷号」攒证据。此前该做法
  实测 18 错 2 对被否决，但那次数据是索引修复前的；现在索引干净了，需要新证据。
"""

import json

import pytest
import pytest_asyncio
from scripts.citation_health_report import _report
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import create_async_engine

from app.models.chat import ChatMessage, ChatSession
from app.models.text import BuddhistText, TextContent

_J13 = "分別業品第四之一。如前所說有情世間及器世間各多差別。"
_J16 = "無學身語業，名身語牟尼，意牟尼即無學意非意業。所以者何？勝義牟尼唯心為體。"
_QUOTE = "無學身語業，名身語牟尼，意牟尼即無學意非意業"

_SOURCES = json.dumps(
    [{"text_id": 38, "juan_num": 16, "chunk_index": 0, "chunk_text": _J16,
      "score": 0.9, "title_zh": "阿毘達磨俱舍論"}]
)


@pytest_asyncio.fixture
async def conn():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as c:
        for model in (BuddhistText, TextContent, ChatSession, ChatMessage):
            await c.run_sync(model.__table__.create)
        await c.execute(sql_text(
            "INSERT INTO buddhist_texts (id, cbeta_id, title_zh, lang) "
            "VALUES (38, 'T1558', '阿毘達磨俱舍論', 'lzh')"))
        for juan, body in ((13, _J13), (16, _J16)):
            await c.execute(sql_text(
                "INSERT INTO text_contents (text_id, juan_num, content, lang, char_count) "
                "VALUES (38, :j, :b, 'lzh', :n)"), {"j": juan, "b": body, "n": len(body)})
        await c.execute(sql_text(
            "INSERT INTO chat_sessions (id, title) VALUES (1, 't')"))
    async with engine.connect() as c:
        yield c
    await engine.dispose()


async def _add(conn, answer: str, mid: int = 1):
    # created_at 走 server_default(now())，天然落在 --days 窗口内。
    await conn.execute(sql_text(
        "INSERT INTO chat_messages (id, session_id, role, content, sources, created_at) "
        "VALUES (:i, 1, 'assistant', :c, :s, CURRENT_TIMESTAMP)"),
        {"i": mid, "c": answer, "s": _SOURCES})


@pytest.mark.asyncio
async def test_quote_in_the_cited_fascicle_counts_as_correct(conn):
    await _add(conn, f"论云「{_QUOTE}」【《阿毘達磨俱舍論》第16卷】")
    r = await _report(conn, days=7, limit=100)
    assert (r["fascicle_checked"], r["fascicle_ok"]) == (1, 1)


@pytest.mark.asyncio
async def test_quote_in_another_fascicle_counts_as_wrong(conn):
    """生产原形：引文逐字正确、卷号指向卷13，而它实出卷十六。"""
    await _add(conn, f"论云「{_QUOTE}」【《阿毘達磨俱舍論》第13卷】")
    r = await _report(conn, days=7, limit=100)
    assert (r["fascicle_checked"], r["fascicle_ok"]) == (1, 0)
    # 但它能被定位到 —— 只是定位结果与标注不一致，这正是第三项要量的。
    assert (r["located"], r["located_agrees"]) == (1, 0)


@pytest.mark.asyncio
async def test_quoteless_citation_counts_against_anchor_coverage(conn):
    """无引号的引用进不了卷号准确率的分母，只会拉低引号覆盖率 —— 两个口径
    必须分开，否则「没引号」会被误读成「引对了」。"""
    await _add(conn, f"经论指出：{_QUOTE}【《阿毘達磨俱舍論》第16卷】")
    r = await _report(conn, days=7, limit=100)
    assert (r["citations"], r["anchored"]) == (1, 0)
    assert r["fascicle_checked"] == 0


@pytest.mark.asyncio
async def test_anchored_citation_counts_toward_coverage(conn):
    await _add(conn, f"论云「{_QUOTE}」【《阿毘達磨俱舍論》第16卷】")
    r = await _report(conn, days=7, limit=100)
    assert (r["citations"], r["anchored"]) == (1, 1)


@pytest.mark.asyncio
async def test_unlocatable_quote_is_excluded_from_the_agreement_rate(conn):
    """全经都找不到（模型转述）的引文，计入卷号准确率的分母（它确实没在所标
    卷里），但不能计入定位一致率 —— 那一项问的是「定位得到时准不准」。"""
    await _add(conn, "论云「這段話原文裡並不存在無論如何都找不到」【《阿毘達磨俱舍論》第16卷】")
    r = await _report(conn, days=7, limit=100)
    assert (r["fascicle_checked"], r["fascicle_ok"]) == (1, 0)
    assert (r["located"], r["located_agrees"]) == (0, 0)


@pytest.mark.asyncio
async def test_citation_outside_the_retrieved_sources_is_ignored(conn):
    """经名不在召回集时无法解析 text_id，判不了就不判 —— 不进任何分母。"""
    await _add(conn, "论云「某段引文長度足夠參與匹配」【《某部未收經》第3卷】")
    r = await _report(conn, days=7, limit=100)
    assert r["citations"] == 0
    assert r["fascicle_checked"] == 0
