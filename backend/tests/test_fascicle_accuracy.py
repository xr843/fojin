"""引文是否真的落在它所标的那一卷里 —— 用 text_contents 做独立真源。

为什么现有指标看不见这件事
--------------------------
`compute_faithfulness` 重放的是运行时护栏，而护栏只检验「引文是否逐字出现在
**召回的 chunk** 里」。2026-07-29 的生产事故正是：引文逐字正确、卷号是错的——
`quote_verifier._find_sources` 在所标卷无匹配时会回退到该经任意卷，于是引文在
卷十六的 chunk 里被找到，答案却标第13卷，两道护栏一起发绿灯。

所以这条指标必须绕开 chunk，直接问 text_contents：这段话在第 N 卷里吗？
不需要金标、不需要人工标注，75 道可答题全覆盖。
"""

import pytest

from app.services.quote_verifier import iter_quote_citations
from eval.faithfulness import compute_fascicle_accuracy

_J16 = "無學身語業，名身語牟尼，意牟尼即無學意非意業。所以者何？勝義牟尼唯心為體。"
_J13 = "分別業品第四之一。如前所說有情世間及器世間各多差別。"
_QUOTE = "無學身語業，名身語牟尼，意牟尼即無學意非意業"


def _lookup(title: str, juan: int) -> str | None:
    return {("阿毘達磨俱舍論", 13): _J13, ("阿毘達磨俱舍論", 16): _J16}.get((title, juan))


class TestIterQuoteCitations:
    def test_pairs_inline_quote_with_its_citation(self):
        got = iter_quote_citations(f"论云「{_QUOTE}」【《阿毘達磨俱舍論》第16卷】")
        assert [(c.title, c.juan) for c in got] == [("阿毘達磨俱舍論", 16)]
        assert got[0].quote == _QUOTE

    def test_pairs_markdown_blockquote_too(self):
        answer = f"论文言：\n> {_QUOTE}。\n\n【《阿毘達磨俱舍論》第16卷】"
        got = iter_quote_citations(answer)
        assert [(c.title, c.juan) for c in got] == [("阿毘達磨俱舍論", 16)]

    def test_count_checked_quotes_stays_in_sync(self):
        """两者必须由同一份配对逻辑得出，否则「检查了几条」与「检查了哪几条」
        会悄悄分叉。"""
        from app.services.quote_verifier import count_checked_quotes

        answer = (
            f"甲云「{_QUOTE}」【《阿毘達磨俱舍論》第16卷】。"
            f"乙云「{_QUOTE}」【《阿毘達磨俱舍論》第13卷】。"
        )
        assert len(iter_quote_citations(answer)) == count_checked_quotes(answer, [])


class TestFascicleAccuracy:
    def test_flags_a_quote_that_is_not_in_the_cited_fascicle(self):
        """生产事故原形：引文逐字正确，卷号指向卷13，而它实出卷十六。"""
        answer = f"论云「{_QUOTE}」【《阿毘達磨俱舍論》第13卷】"
        got = compute_fascicle_accuracy(answer, _lookup)
        assert got["fascicle_checked"] == 1
        assert got["fascicle_correct"] == 0

    def test_accepts_a_quote_that_is_in_the_cited_fascicle(self):
        answer = f"论云「{_QUOTE}」【《阿毘達磨俱舍論》第16卷】"
        got = compute_fascicle_accuracy(answer, _lookup)
        assert got == {"fascicle_checked": 1, "fascicle_correct": 1}

    def test_tolerates_punctuation_and_script_differences(self):
        """LLM 常写简体、改标点；判据必须与 quote_verifier 用同一套归一化，
        否则会把正确的引文误判成错卷。"""
        answer = "论云「无学身语业名身语牟尼意牟尼即无学意非意业」【《阿毘達磨俱舍論》第16卷】"
        got = compute_fascicle_accuracy(answer, _lookup)
        assert got["fascicle_correct"] == 1

    def test_skips_what_it_cannot_adjudicate(self):
        """查不到该卷正文时不计入分母——沉默地记为「错」会让指标失真。"""
        answer = f"论云「{_QUOTE}」【《某部未收經》第3卷】"
        assert compute_fascicle_accuracy(answer, _lookup) == {
            "fascicle_checked": 0,
            "fascicle_correct": 0,
        }

    def test_citation_without_a_fascicle_is_not_checkable(self):
        answer = f"论云「{_QUOTE}」【《阿毘達磨俱舍論》】"
        assert compute_fascicle_accuracy(answer, _lookup)["fascicle_checked"] == 0


@pytest.mark.parametrize("answer", ["", "没有任何引用的答案。"])
def test_empty_answers_are_inert(answer):
    assert compute_fascicle_accuracy(answer, _lookup) == {
        "fascicle_checked": 0,
        "fascicle_correct": 0,
    }
