"""接线测试：``retrieve_rag_context`` 真的把无法引用的外语来源挡在外面。

`test_rag_uncitable_foreign.py` 测的是纯函数本身；一个纯函数写对了但没被调用，
单测照样全绿而生产照样出事（[[gates-green-but-prod-breaks]] 里那三类盲区之一）。
所以这里跑**真实的编排**，只把 I/O 边界换掉：embedding、四个 DB 查询、
两个 attach、词典查询、本经保底注入。reranker 在测试环境下 ``reranker_api_url=""``，
走纯函数 ``_keyword_rerank``，不用替换。

复现的是 2026-09-22 生产实测的那个形状：汉文提问，lzh 臂返回 0 行（HNSW 图够不到），
池子里只剩 pi/bo，五条引用全是 ``Toh …(Kangyur)`` / 英文 SuttaCentral 条目。
"""

import contextlib
import logging

import pytest

from app.services import rag_retrieval as R


def _chunk(text_id: int, lang: str, title_zh: str, score: float) -> dict:
    return {
        "text_id": text_id,
        "juan_num": 1,
        "chunk_index": 0,
        "chunk_text": "片段内容",
        "score": score,
        "title_zh": title_zh,
        "lang": lang,
        "source_id": None,
        "cbeta_id": f"X{text_id}",
    }


@pytest.fixture
def stub_io(monkeypatch):
    """把 retrieve_rag_context 的每个 I/O 边界换成内存桩，编排逻辑保持真实。"""

    async def _no_precise(db, query, *, scope_text_ids=None):
        return None

    async def _embed(text):
        return [0.0] * 8

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield object()

    async def _no_sources(session, emb, limit=3, min_score=0.5):
        return []

    async def _noop_attach(db, results, *args, **kwargs):
        return None

    async def _no_dict(db, query):
        return ""

    async def _no_injection(db, query, emb, results):
        return results

    monkeypatch.setattr(R, "try_precise_text_retrieval", _no_precise)
    monkeypatch.setattr(R, "generate_embedding", _embed)
    monkeypatch.setattr(R, "async_session", _fake_session)
    monkeypatch.setattr(R, "source_similarity_search", _no_sources)
    monkeypatch.setattr(R, "_attach_parallel_chunks", _noop_attach)
    monkeypatch.setattr(R, "_attach_mitra_parallels", _noop_attach)
    monkeypatch.setattr(R, "_lookup_dictionary_terms", _no_dict)
    monkeypatch.setattr(R, "_inject_root_sutra_slot", _no_injection)


def _install_pool(monkeypatch, *, lzh: list[dict], pi: list[dict], bo: list[dict]):
    async def _search(session, emb, limit=5, scope_text_ids=None, lang_list=None):
        if lang_list == ["lzh"]:
            return lzh
        if lang_list == ["pi"]:
            return pi
        if lang_list == ["bo"]:
            return bo
        return lzh + pi + bo

    monkeypatch.setattr(R, "similarity_search", _search)


@pytest.mark.asyncio
async def test_chinese_question_with_only_foreign_pool_serves_no_sources(monkeypatch, stub_io):
    """生产 222 条的形状：lzh 臂 0 行，池子全是藏文/巴利 → 一条都不给。"""
    _install_pool(
        monkeypatch,
        lzh=[],
        pi=[_chunk(101, "pi", "With Sakka ", 0.42)],
        bo=[
            _chunk(201, "bo", "Toh 113 (Kangyur)", 0.44),
            _chunk(202, "bo", "Toh 172 (Kangyur)", 0.43),
        ],
    )
    sources, context_text = await R.retrieve_rag_context(object(), "华严宗与天台宗的判教体系有什么不同？")
    assert sources == []
    assert "Toh 113" not in context_text
    assert "With Sakka" not in context_text


@pytest.mark.asyncio
async def test_chinese_question_promotes_chinese_over_foreign(monkeypatch, stub_io):
    """混合池：汉文来源该被留下，外语来源不占格子。"""
    _install_pool(
        monkeypatch,
        lzh=[_chunk(1, "lzh", "大般涅槃經", 0.50), _chunk(2, "lzh", "成唯識論", 0.48)],
        pi=[_chunk(101, "pi", "Dispute ", 0.60)],
        bo=[_chunk(201, "bo", "Toh 220 (Kangyur)", 0.62)],
    )
    sources, _ = await R.retrieve_rag_context(object(), "涅槃有哪些分类？")
    assert [s.title_zh for s in sources] == ["大般涅槃經", "成唯識論"]


@pytest.mark.asyncio
async def test_english_question_still_gets_pali_sources(monkeypatch, stub_io):
    """非汉文提问不受影响——那时 SuttaCentral 条目正是该给的东西。"""
    _install_pool(
        monkeypatch,
        lzh=[],
        pi=[_chunk(101, "pi", "With Sakka ", 0.42)],
        bo=[_chunk(201, "bo", "Toh 113 (Kangyur)", 0.44)],
    )
    sources, _ = await R.retrieve_rag_context(object(), "What is dependent origination?")
    assert {s.title_zh for s in sources} == {"With Sakka ", "Toh 113 (Kangyur)"}


@pytest.mark.asyncio
async def test_chinese_arm_collapse_is_logged_even_when_whole_pool_is_empty(monkeypatch, stub_io, caplog):
    """根因埋点：lzh 臂返回 0 行本身就该被计数。

    ``drop_uncitable_foreign_sources`` 只在「有外语来源被丢掉」时打点；三条臂**全空**
    时（生产的「阿含经与般若经在思想上有什么发展变化？」就是这样）它拿到空列表直接
    早退，什么也不记。可那是同一个缺陷的更严重形态。要量真实发生率，必须在臂上打点。
    """
    _install_pool(monkeypatch, lzh=[], pi=[], bo=[])
    with caplog.at_level(logging.WARNING, logger="app.services.rag_retrieval"):
        sources, _ = await R.retrieve_rag_context(object(), "阿含经与般若经在思想上有什么发展变化？")
    assert sources == []
    assert any("lzh_arm_empty" in rec.getMessage() for rec in caplog.records)


@pytest.mark.asyncio
async def test_healthy_chinese_arm_is_not_logged(monkeypatch, stub_io, caplog):
    """正常召回不得污染那条计数。"""
    _install_pool(monkeypatch, lzh=[_chunk(1, "lzh", "雜阿含經", 0.5)], pi=[], bo=[])
    with caplog.at_level(logging.WARNING, logger="app.services.rag_retrieval"):
        await R.retrieve_rag_context(object(), "什么是四念处？")
    assert not any("lzh_arm_empty" in rec.getMessage() for rec in caplog.records)


@pytest.mark.asyncio
async def test_followup_without_cjk_in_a_chinese_session_is_still_guarded(monkeypatch, stub_io):
    """多轮会话里的追问可能一个汉字都没有（「ok?」「1」），但整场对话是中文的。

    检索用的 embedding 本来就是 ``prev_query + query`` 拼出来的，护栏的语言判断必须
    跟它同源，否则会出现「埋点报了但护栏没拦」的错位——答案仍然是中文的，读者仍然
    拿不到可用的出处。
    """
    _install_pool(
        monkeypatch,
        lzh=[],
        pi=[_chunk(101, "pi", "With Sakka ", 0.42)],
        bo=[_chunk(201, "bo", "Toh 113 (Kangyur)", 0.44)],
    )
    sources, _ = await R.retrieve_rag_context(object(), "more?", prev_query="华严宗与天台宗的判教体系有什么不同？")
    assert sources == []
