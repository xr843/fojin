"""异体字归并 + 整卷兜底：一字不差的引文不该因为「写法不同」或「那一段没被召回」被降级。

用例里的引文都取自生产降级记录（chat_answer_diagnostics，2026-07-10 至 10-07）。
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.schemas.chat import ChatSource
from app.services.passage_locator import fast_normalise
from app.services.quote_fulljuan import (
    MAX_ELIDED_SPAN,
    load_full_juan_check,
    make_full_juan_check,
)
from app.services.quote_verifier import _normalise, juans_to_recheck, verify_quoted_content


def _src(text_id: int, title: str, juan: int, chunk_text: str) -> ChatSource:
    return ChatSource(
        text_id=text_id,
        juan_num=juan,
        chunk_index=0,
        chunk_text=chunk_text,
        score=0.9,
        title_zh=title,
        lang="lzh",
    )


# ──────────────────────────────────────────────────────────────────────
# 异体字归并
# ──────────────────────────────────────────────────────────────────────


def test_variant_only_quote_is_verified():
    """嘉泰普燈錄 卷2：模型写「周遍」，CBETA 作「周徧」——同一个字。"""
    answer = "「如来藏中，性水真空，性空真水，清净本然，周遍法界」【《嘉泰普燈錄》第2卷】"
    src = _src(1, "嘉泰普燈錄", 2, "如來藏中，性水真空，性空真水，清淨本然，周徧法界，隨眾生心。")
    out, muts = verify_quoted_content(answer, [src])
    assert muts == []
    assert out == answer


def test_several_variants_in_one_quote():
    answer = "「心体离念，离念相者，等虚空界无所不遍」【《阿彌陀經疏鈔演義》第1卷】"
    src = _src(2, "阿彌陀經疏鈔演義", 1, "心體離念，離念相者，等虗空界無所不徧，法界一相。")
    _, muts = verify_quoted_content(answer, [src])
    assert muts == []


def test_different_character_is_not_folded():
    """曾/甞 是两个字（未曾 ≠ 未嘗），回放里出现过也不收——仍要降级。"""
    answer = "「眾菩薩未曾說一字，老維摩其聲如雷」【《宗門拈古彙集》第3卷】"
    src = _src(3, "宗門拈古彙集", 3, "眾菩薩未甞說一字，老維摩其聲如雷。")
    _, muts = verify_quoted_content(answer, [src])
    assert len(muts) == 1


def test_fold_is_length_preserving_and_shared_with_locator():
    """passage_locator 按位置回指原文，归并必须逐字 1→1，且两处口径一致。"""
    raw = "虗徧煖煗竝著瞋祇婬沈麤葢繇玅挍柰黙瞖劒戹隣雑彊蕰"
    assert len(_normalise(raw)) == len(raw)
    assert fast_normalise(raw) == _normalise(raw)


# ──────────────────────────────────────────────────────────────────────
# 整卷兜底
# ──────────────────────────────────────────────────────────────────────

# 《楞嚴經觀心定解》卷8：检索片段里没有这一句，整卷里一字不差。
_QUOTE = "臨命終時，未捨煖觸，一生善惡，俱時頓現"
_ANSWER = f"经中说「{_QUOTE}」【《楞嚴經觀心定解》第8卷】。"
_CHUNK = _src(10, "楞嚴經觀心定解", 8, "此卷别处的一段，与引文无关的内容。")
_BODY = "前文若干。" + _QUOTE + "，死逆生順，二習相交。後文若干。"


def _check(bodies: dict[tuple[int, int], str]):
    return make_full_juan_check({k: fast_normalise(v) for k, v in bodies.items()})


def test_quote_missing_from_chunks_but_in_cited_juan_is_verified():
    out, muts = verify_quoted_content(_ANSWER, [_CHUNK], full_juan_check=_check({(10, 8): _BODY}))
    assert muts == []
    assert out == _ANSWER


def test_without_fallback_the_same_quote_is_downgraded():
    """对照臂：不给兜底时行为与改动前完全一致。"""
    _, muts = verify_quoted_content(_ANSWER, [_CHUNK])
    assert len(muts) == 1


def test_quote_absent_from_whole_juan_stays_downgraded():
    body = "前文若干。臨命終時，一生善惡，悉皆頓現。後文若干。"
    _, muts = verify_quoted_content(_ANSWER, [_CHUNK], full_juan_check=_check({(10, 8): body}))
    assert len(muts) == 1


def test_quote_only_in_another_juan_stays_downgraded():
    """卷号写错的引文不在这里救——只查答案写明的那一卷。"""
    _, muts = verify_quoted_content(_ANSWER, [_CHUNK], full_juan_check=_check({(10, 9): _BODY}))
    assert len(muts) == 1


def test_quote_in_unretrieved_text_with_same_juan_stays_downgraded():
    """text_id 只取自检索片段：别的书同卷里有这句，不算。"""
    _, muts = verify_quoted_content(_ANSWER, [_CHUNK], full_juan_check=_check({(99, 8): _BODY}))
    assert len(muts) == 1


def test_elided_quote_verified_within_span():
    answer = "「臨命終時，未捨煖觸……死逆生順，二習相交」【《楞嚴經觀心定解》第8卷】"
    _, muts = verify_quoted_content(answer, [_CHUNK], full_juan_check=_check({(10, 8): _BODY}))
    assert muts == []


def test_elided_segments_too_far_apart_stay_downgraded():
    """整卷几万字，各段按序出现不够——首尾跨度超出上限就不认。"""
    body = "臨命終時，未捨煖觸。" + "中" * (MAX_ELIDED_SPAN + 10) + "死逆生順，二習相交。"
    answer = "「臨命終時，未捨煖觸……死逆生順，二習相交」【《楞嚴經觀心定解》第8卷】"
    _, muts = verify_quoted_content(answer, [_CHUNK], full_juan_check=_check({(10, 8): body}))
    assert len(muts) == 1


# ──────────────────────────────────────────────────────────────────────
# 该读哪几卷
# ──────────────────────────────────────────────────────────────────────


def test_juans_to_recheck_lists_only_failing_quotes_of_retrieved_titles():
    ok = "「此卷别处的一段，与引文无关的内容」【《楞嚴經觀心定解》第8卷】"
    unretrieved = "「一二三四五六七八九十十一十二」【《未检索到的书》第3卷】"
    no_juan = f"「{_QUOTE}」【《楞嚴經觀心定解》】"
    answer = "\n".join([_ANSWER, _ANSWER, ok, unretrieved, no_juan])
    assert juans_to_recheck(answer, [_CHUNK]) == [(10, 8)]


def test_load_returns_none_when_nothing_to_recheck():
    db = MagicMock()
    db.execute = AsyncMock()
    ok = "「此卷别处的一段，与引文无关的内容」【《楞嚴經觀心定解》第8卷】"
    assert asyncio.run(load_full_juan_check(db, juans_to_recheck(ok, [_CHUNK]))) is None
    db.execute.assert_not_called()


def test_load_failure_degrades_to_no_fallback():
    """读库失败绝不打断回答：返回 None，verifier 照旧降级。"""
    db = MagicMock()
    db.execute = AsyncMock(side_effect=RuntimeError("db down"))
    assert asyncio.run(load_full_juan_check(db, juans_to_recheck(_ANSWER, [_CHUNK]))) is None


def test_load_builds_check_from_rows():
    result = MagicMock()
    result.all.return_value = [(10, 8, _BODY)]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    check = asyncio.run(load_full_juan_check(db, juans_to_recheck(_ANSWER, [_CHUNK])))
    _, muts = verify_quoted_content(_ANSWER, [_CHUNK], full_juan_check=check)
    assert muts == []
