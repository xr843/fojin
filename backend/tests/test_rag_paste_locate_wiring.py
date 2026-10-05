"""接线测试：贴原文定位真的进了 ``retrieve_rag_context`` 的上下文，且只加证据、不挡答案。

纯函数在 test_passage_locator.py；这里跑真实编排，只换 I/O 边界（沿用
test_rag_uncitable_foreign_wiring 的桩）。
"""

import pytest

from app.services import passage_locator as PL
from app.services import rag_retrieval as R
from tests.test_rag_uncitable_foreign_wiring import _chunk, _install_pool, stub_io  # noqa: F401

PASTE = "凡所有相，皆是虚妄。若见诸相非相，则见如来。这句怎么理解？"


def _located() -> PL.Located:
    chunk = _chunk(7, "lzh", "金剛般若波羅蜜經", 1.0) | {
        "chunk_index": 3,
        "chunk_text": "凡所有相，皆是虛妄。若見諸相非相，則見如來。",
        "cbeta_id": "T0235",
    }
    return PL.Located(chunk=chunk, window_text="凡所有相，皆是虚妄", window_han=18, texts_with_window=2)


def _pool(monkeypatch):
    _install_pool(
        monkeypatch,
        lzh=[_chunk(i, "lzh", f"注疏{i}", 0.6 - i / 100) for i in range(1, 7)],
        pi=[],
        bo=[],
    )


@pytest.mark.asyncio
async def test_located_passage_takes_slot_one(monkeypatch, stub_io):  # noqa: F811
    _pool(monkeypatch)

    async def _locate(es, db, message):
        assert message == PASTE
        return _located()

    monkeypatch.setattr(R, "locate_pasted_passage", _locate)
    monkeypatch.setattr(R, "get_es", lambda: object())
    sources, context = await R.retrieve_rag_context(object(), PASTE)
    assert sources[0].title_zh == "金剛般若波羅蜜經" and sources[0].chunk_index == 3
    assert len(sources) == R.MAX_CONTEXT_CHUNKS
    assert "則見如來" in context
    # 注入块带「逐字出现 ≠ 出处」的说明，其他块不带
    assert context.count("[用户原文定位]") == 1
    assert "不要把本书说成它的出处" in context


@pytest.mark.asyncio
async def test_locator_failure_degrades_to_plain_vector_rag(monkeypatch, stub_io):  # noqa: F811
    _pool(monkeypatch)

    async def _boom(es, db, message):
        raise RuntimeError("es down")

    monkeypatch.setattr(R, "locate_pasted_passage", _boom)
    monkeypatch.setattr(R, "get_es", lambda: object())
    sources, _ = await R.retrieve_rag_context(object(), PASTE)
    assert [s.title_zh for s in sources][:2] == ["注疏1", "注疏2"]


@pytest.mark.asyncio
async def test_master_scope_never_runs_the_locator(monkeypatch, stub_io):  # noqa: F811
    _pool(monkeypatch)
    called = []

    async def _locate(es, db, message):
        called.append(message)
        return _located()

    monkeypatch.setattr(R, "locate_pasted_passage", _locate)
    monkeypatch.setattr(R, "get_es", lambda: object())
    sources, _ = await R.retrieve_rag_context(object(), PASTE, scope_text_ids=[1, 2])
    assert called == []
    assert all(s.title_zh != "金剛般若波羅蜜經" for s in sources)


@pytest.mark.asyncio
async def test_flag_off_disables_the_locator(monkeypatch, stub_io):  # noqa: F811
    _pool(monkeypatch)
    called = []

    async def _locate(es, db, message):
        called.append(message)
        return _located()

    monkeypatch.setattr(R, "locate_pasted_passage", _locate)
    monkeypatch.setattr(R, "get_es", lambda: object())
    monkeypatch.setattr(R, "ENABLE_PASTE_LOCATE", False)
    await R.retrieve_rag_context(object(), PASTE)
    assert called == []
