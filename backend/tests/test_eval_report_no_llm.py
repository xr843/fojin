"""`--no-llm` 报告不得把「没测」印成「零分」。

夜间门禁跑的就是 `--no-llm`，所以生产 `eval/reports/` 里最近每一份报告的抬头
都写着 **综合得分: 0.0%**，底下跟着一张四维全 0 的表 —— 2026-08-21 翻最新报告
时就是这么读到的。它的真实含义是「这一轮没有生成回答，因此无从评分」，但纸面上
读起来是「这个系统得零分」。

这不是新问题的新形状：`test_eval_llm_call_config.py` 记的那次事故里，一份
「90 道题全是空答案」的报告同样把各项印成 0，而我们差点拿它去比较推理档位。
零和「未测量」在报告里必须长得不一样。

`_faithfulness_section` 早就守着这条规矩（空数据时印一行说明而不是零），
本测试把同一条规矩钉在 LLM 评审那两张表上。
"""

from eval.run_eval import generate_report

_RETRIEVAL = {"recall@5": 0.26, "hit@5": 0.342, "mrr": 0.214, "num_gold": 2}


def _row(scores: dict) -> dict:
    return {
        "id": "q1",
        "category": "term_explanation",
        "question": "五蕴是什么？",
        "scores": scores,
        "retrieval_metrics": _RETRIEVAL,
        "timing": {"total_s": 1.5},
    }


_SKIPPED = {
    "retrieval_relevance": -1,
    "citation_accuracy": -1,
    "answer_completeness": -1,
    "no_hallucination": -1,
    "reason": "LLM skipped",
}
_JUDGED = {
    "retrieval_relevance": 3,
    "citation_accuracy": 3,
    "answer_completeness": 2,
    "no_hallucination": 1,
}


class TestNoLlmRun:
    def test_does_not_claim_a_zero_overall_score(self):
        report = generate_report([_row(_SKIPPED)])
        assert "**综合得分**: 0.0%" not in report
        assert "未生成回答" in report

    def test_says_why_the_scores_are_absent(self):
        report = generate_report([_row(_SKIPPED)])
        # The four judged dimensions must not appear as a table of zeros.
        assert "| 检索相关性 | 0 | 3 |" not in report
        assert "| 检索相关性 | 0.0 | 3 |" not in report
        assert "无评分数据" in report

    def test_still_reports_deterministic_retrieval_metrics(self):
        # The whole point of a --no-llm run: these are measured and must survive.
        report = generate_report([_row(_SKIPPED)])
        assert "0.342" in report
        assert "检索指标" in report

    def test_category_table_keeps_question_counts(self):
        # Whole line, not a prefix: "| 名相解释 | 2 |" is also a prefix of the
        # old zero-padded row, so a substring check would pass either way and
        # discriminate nothing.
        report = generate_report([_row(_SKIPPED), _row(_SKIPPED)])
        assert "\n| 名相解释 | 2 |\n" in report


class TestJudgedRun:
    def test_reports_the_percentage(self):
        report = generate_report([_row(_JUDGED)])
        # 3 + 3 + 2 + 1*3 = 11 out of 12. ("未生成回答" still appears further
        # down, in the faithfulness section — these rows carry no faithfulness
        # data, and that section has always said so.)
        assert "**综合得分**: 91.7%" in report
        assert "综合得分**: —" not in report

    def test_keeps_the_score_tables(self):
        report = generate_report([_row(_JUDGED)])
        assert "| 检索相关性 | 3.0 | 3 |" in report
        assert "| 名相解释 | 1 | 3.0 | 3.0 | 2.0 | 1.0 |" in report
