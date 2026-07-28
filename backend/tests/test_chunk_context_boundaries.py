"""chunk_context 的边界标志必须来自数据，不能来自算术。

线上曾出现：从 /chat 点开《阿毘達磨俱舍論》第16卷的引文，抽屉只显示一行
「… 前文（本卷第 0 段之前）」，正文一个字也没有。

根因是 ``has_more_before = low > 0`` —— 一行纯算术，从不查库。只要
``chunk_index > radius`` 它就报 true，哪怕该 (text_id, juan_num, chunk_index)
在库里根本不存在。而 ``has_more_after`` 是真的做了存在性探针，两者不对称。

这类缺陷的危害不在于崩溃，而在于**它不崩溃**：接口返回 200、前端不报错，
只是把「内容就在视野外」这句谎话画在空白正文上方。而「可核对引用」正是
这个产品唯一在转的护城河——引文核对不了，护城河在这个入口上就是断的。

因此这里钉住的不变量是：**没有 chunk 时，两个方向都不许声称还有更多。**
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.api.texts import get_chunk_context


def _conn(title: str | None, chunk_rows: list, before_hit: bool, after_hit: bool):
    """构造一个按调用顺序返回预设结果的假连接。

    端点依次发出四条 SQL：标题、窗口内 chunks、before 探针、after 探针。
    """
    results = [
        MagicMock(fetchone=MagicMock(return_value=(title,) if title is not None else None)),
        MagicMock(fetchall=MagicMock(return_value=chunk_rows)),
        MagicMock(fetchone=MagicMock(return_value=(1,) if before_hit else None)),
        MagicMock(fetchone=MagicMock(return_value=(1,) if after_hit else None)),
    ]
    conn = AsyncMock()
    conn.exec_driver_sql = AsyncMock(side_effect=results)
    db = AsyncMock()
    db.connection = AsyncMock(return_value=conn)
    return db


@pytest.mark.asyncio
async def test_missing_chunk_does_not_claim_more_before():
    """请求的 chunk 不存在时，has_more_before 必须为 False。

    修复前此处恒为 True（low = 7-2 = 5 > 0），前端据此画出边界提示，
    读者看到的是「前文就在视野外」——而实际上什么都没找到。
    """
    db = _conn("阿毘達磨俱舍論", [], before_hit=False, after_hit=False)
    resp = await get_chunk_context(
        text_id=1558, juan_num=16, chunk_index=7, radius=2, db=db
    )
    assert resp.chunks == []
    assert resp.has_more_before is False
    assert resp.has_more_after is False


@pytest.mark.asyncio
async def test_before_flag_reflects_probe_not_arithmetic():
    """探针命中才算「前面还有」，与 chunk_index 的大小无关。"""
    db = _conn("某經", [(5, "甲"), (6, "乙"), (7, "丙")], before_hit=True, after_hit=False)
    resp = await get_chunk_context(
        text_id=1, juan_num=1, chunk_index=6, radius=2, db=db
    )
    assert resp.has_more_before is True
    assert resp.has_more_after is False


@pytest.mark.asyncio
async def test_juan_start_has_nothing_before():
    """卷首（chunk_index=0）不许声称前面还有内容。"""
    db = _conn("某經", [(0, "如是我聞")], before_hit=False, after_hit=True)
    resp = await get_chunk_context(
        text_id=1, juan_num=1, chunk_index=0, radius=2, db=db
    )
    assert resp.has_more_before is False
    assert resp.has_more_after is True


@pytest.mark.asyncio
async def test_center_chunk_is_marked():
    """被引的那一段要标出来，前端据此高亮。"""
    db = _conn("某經", [(4, "前"), (5, "中"), (6, "後")], before_hit=True, after_hit=True)
    resp = await get_chunk_context(
        text_id=1, juan_num=1, chunk_index=5, radius=1, db=db
    )
    assert [c.is_center for c in resp.chunks] == [False, True, False]
