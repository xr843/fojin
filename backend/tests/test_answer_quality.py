"""Answer-quality queue — pure classifier unit tests + API tests."""



from app.services.answer_quality import (
    WEAK_EVIDENCE_THRESHOLD,
    _max_source_score,
    _percentiles,
    classify_answer,
)


def _sources(*scores):
    return [{"text_id": 1, "juan_num": 1, "chunk_text": "x", "score": s} for s in scores]


def test_strong_answer_is_not_suspect():
    tags, score = classify_answer(
        "这是一段足够长且引用了可靠经文的回答，详细解释了五蕴的含义、出处"
        "与彼此关系，并逐一给出对应的经证与上下文脉络，便于读者核对。",
        _sources(0.82, 0.61),
        None,
    )
    assert tags == []
    assert score == 0.0


def test_downvoted_is_flagged():
    tags, score = classify_answer("一段足够长的正常回答" * 3, _sources(0.9), "down")
    assert "downvoted" in tags
    assert score > 0


def test_no_citation_is_flagged():
    tags, _ = classify_answer("一段足够长的正常回答内容" * 3, None, None)
    assert "no_citation" in tags


def test_weak_evidence_is_flagged_and_graded():
    near, score_near = classify_answer(
        "正常长度的回答内容" * 3, _sources(WEAK_EVIDENCE_THRESHOLD - 0.05), None
    )
    far, score_far = classify_answer("正常长度的回答内容" * 3, _sources(0.01), None)
    assert "weak_evidence" in near and "weak_evidence" in far
    assert score_far > score_near  # deeper below threshold => more suspect


def test_abnormal_short_answer_is_flagged():
    tags, _ = classify_answer("太短了", _sources(0.9), None)
    assert "abnormal" in tags


def test_abnormal_error_marker_is_flagged():
    tags, _ = classify_answer("发送失败，请稍后重试" + "x" * 50, _sources(0.9), None)
    assert "abnormal" in tags


def test_multiple_detectors_stack():
    tags, score = classify_answer("短", None, "down")
    assert {"downvoted", "abnormal", "no_citation"} <= set(tags)
    assert score > 5  # all three weights add up


def test_max_source_score_handles_bad_json():
    assert _max_source_score(None) is None
    assert _max_source_score([]) is None
    assert _max_source_score([{"no_score": 1}]) is None
    assert _max_source_score(_sources(0.3, 0.7)) == 0.7


def test_percentiles_empty_returns_nulls():
    assert _percentiles([]) == {"p10": None, "p25": None, "p50": None, "p90": None}


def test_percentiles_basic():
    p = _percentiles([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
    assert p["p10"] <= p["p50"] <= p["p90"]
