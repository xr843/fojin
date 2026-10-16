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


# ---- 定位结果带到前端（定位卡片）：located 字段随 sources 流式下发并入库 ----


@pytest.mark.asyncio
async def test_located_source_carries_card_fields(monkeypatch, stub_io):  # noqa: F811
    _pool(monkeypatch)

    async def _locate(es, db, message):
        return PL.Located(
            chunk=_located().chunk,
            window_text="凡所有相，皆是虚妄",
            window_han=18,
            texts_with_window=2,
            source_span="凡所有相，\n皆是虛妄",
        )

    monkeypatch.setattr(R, "locate_pasted_passage", _locate)
    monkeypatch.setattr(R, "get_es", lambda: object())
    sources, _ = await R.retrieve_rag_context(object(), PASTE)
    top = sources[0]
    assert top.located is True
    # 展示的是语料自己的字（繁体、原标点），CBETA 硬换行去掉 —— 抽屉高亮按它找
    assert top.located_window == "凡所有相，皆是虛妄"
    assert top.located_texts == 2
    dumped = top.model_dump()
    assert dumped["located"] is True and dumped["located_texts"] == 2
    # 其他来源不带定位字段
    assert all(s.located is False and s.located_window is None and s.located_texts is None for s in sources[1:])
    # 内部的 located_quote 只给模型上下文用，不进 schema
    assert "located_quote" not in dumped


@pytest.mark.asyncio
async def test_located_window_falls_back_to_user_text_without_span(monkeypatch, stub_io):  # noqa: F811
    _pool(monkeypatch)

    async def _locate(es, db, message):
        return _located()  # source_span 缺省

    monkeypatch.setattr(R, "locate_pasted_passage", _locate)
    monkeypatch.setattr(R, "get_es", lambda: object())
    sources, _ = await R.retrieve_rag_context(object(), PASTE)
    assert sources[0].located is True
    assert sources[0].located_window == "凡所有相，皆是虚妄"


@pytest.mark.asyncio
async def test_no_located_fields_when_locator_misses(monkeypatch, stub_io):  # noqa: F811
    _pool(monkeypatch)

    async def _miss(es, db, message):
        return None

    monkeypatch.setattr(R, "locate_pasted_passage", _miss)
    monkeypatch.setattr(R, "get_es", lambda: object())
    sources, _ = await R.retrieve_rag_context(object(), PASTE)
    assert sources and not any(s.located for s in sources)
    assert all(s.located_window is None and s.located_texts is None for s in sources)


def test_stored_sources_without_located_still_load():
    """入库的旧 sources（无 located 字段）读回来仍合法，默认不定位。"""
    from app.schemas.chat import ChatSource

    s = ChatSource(text_id=1, juan_num=1, chunk_text="x", score=0.5)
    assert s.located is False and s.located_window is None and s.located_texts is None
