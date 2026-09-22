"""汉文提问不得把无法引用的外语条目当主引用交出去。

2026-09-22 生产实测：60 天 3,127 条有引用的回答里，**222 条（7.1%）的引用全部是
藏文 Kangyur 编号或英文 SuttaCentral 条目**，另有 71 条回答里出现了
``【《Toh 134 (Kangyur)》第1卷】`` ``【《With Kimbila 》第1卷】`` 这样的引用——
汉文引用格式套在一个没有汉文题名的文本上，对读者毫无用处。

成因不在这一层（是 HNSW 图对部分查询够不到真正的最近邻，lzh 臂返回 0 行，
池子里只剩 pi/bo），但**这条护栏与索引怎么修无关**：检索失败时系统不该假装成功。

判据用 ``lang``：全库实测 lzh 文本 4,182 部**全部**有汉字题名，pi/bo/sa 共 6,349 部
**无一**有汉字题名，所以「非 lzh」与「拿不出 ``【《经名》第N卷】`` 引用」在本语料里等价。
跨藏对读不受影响——它走 ``parallel_chunks`` / ``mitra_parallels`` 两个独立字段，
挂在 lzh 主引用上，不是主引用本身。
"""

import logging

from app.services.rag_retrieval import drop_uncitable_foreign_sources


def _r(text_id: int, lang: str, title_zh: str = "", score: float = 0.5) -> dict:
    return {
        "text_id": text_id,
        "juan_num": 1,
        "chunk_index": 0,
        "chunk_text": "…",
        "score": score,
        "title_zh": title_zh,
        "lang": lang,
    }


CJK_Q = "华严宗与天台宗的判教体系有什么不同？"


def test_cjk_query_all_foreign_sources_yields_nothing():
    """生产上的 222 条就是这个形状——五条全是 Toh/英文条目。"""
    results = [
        _r(1, "bo", "Toh 113 (Kangyur)"),
        _r(2, "bo", "Toh 172 (Kangyur)"),
        _r(3, "bo", "Toh 8 (Kangyur)"),
        _r(4, "bo", "Toh 556 (Kangyur)"),
        _r(5, "pi", "With Sakka "),
    ]
    assert drop_uncitable_foreign_sources(CJK_Q, results) == []


def test_cjk_query_mixed_keeps_only_chinese():
    """混合情况（生产 60 天 49 条）：汉文的留下，外语的丢掉，顺序不变。"""
    results = [
        _r(1, "bo", "Toh 220 (Kangyur)", score=0.9),
        _r(2, "lzh", "大般涅槃經", score=0.8),
        _r(3, "pi", "Dispute ", score=0.7),
        _r(4, "lzh", "成唯識論", score=0.6),
    ]
    out = drop_uncitable_foreign_sources(CJK_Q, results)
    assert [r["text_id"] for r in out] == [2, 4]


def test_cjk_query_all_chinese_is_untouched():
    """绝不动汉文来源——护栏只做减法，且只减不可引用的那些。"""
    results = [_r(1, "lzh", "中論"), _r(2, "lzh", "大智度論")]
    assert drop_uncitable_foreign_sources(CJK_Q, results) == results


def test_non_cjk_query_keeps_foreign_sources():
    """英文提问问巴利经典，SuttaCentral 条目正是该给的东西。"""
    results = [_r(1, "pi", "With Sakka "), _r(2, "bo", "Toh 113 (Kangyur)")]
    assert drop_uncitable_foreign_sources("What is dependent origination?", results) == results


def test_empty_input_is_empty_output():
    assert drop_uncitable_foreign_sources(CJK_Q, []) == []


def test_missing_lang_key_is_treated_as_chinese():
    """``similarity_search`` 对 lang 为空的行已经兜底成 'lzh'；这里跟它保持一致，
    宁可多留一条也不要静默丢掉一条本该给出的汉文来源。"""
    r = {"text_id": 9, "juan_num": 1, "score": 0.5, "title_zh": "雜阿含經"}
    assert drop_uncitable_foreign_sources(CJK_Q, [r]) == [r]


def test_dropping_everything_is_logged_for_telemetry(caplog):
    """埋点：没有它就只能靠翻库抽样，看不到真实发生率。"""
    results = [_r(1, "bo", "Toh 113 (Kangyur)"), _r(2, "pi", "With Sakka ")]
    with caplog.at_level(logging.WARNING, logger="app.services.rag_retrieval"):
        drop_uncitable_foreign_sources(CJK_Q, results)
    assert any("uncitable_foreign_only" in rec.message for rec in caplog.records)


def test_partial_drop_is_not_logged_as_total_failure():
    """只丢掉一部分不是检索失败，不该污染那条埋点的计数。"""
    results = [_r(1, "bo", "Toh 113 (Kangyur)"), _r(2, "lzh", "中論")]
    import logging as _logging

    records: list[_logging.LogRecord] = []

    class _Cap(_logging.Handler):
        def emit(self, record):
            records.append(record)

    logger = _logging.getLogger("app.services.rag_retrieval")
    h = _Cap()
    logger.addHandler(h)
    try:
        drop_uncitable_foreign_sources(CJK_Q, results)
    finally:
        logger.removeHandler(h)
    assert not any("uncitable_foreign_only" in r.getMessage() for r in records)
