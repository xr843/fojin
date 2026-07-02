"""Regression locks for the RAG ranking pure functions.

`_keyword_rerank` is the DEFAULT rerank path (used whenever no cross-encoder
API is configured) — it is the actual decider of which sutra chunks reach the
LLM, yet had zero tests. `_merge_with_alignment_sync` orders the trilingual
candidate pool. Both are pure (list[dict] -> list[dict], no DB/IO), so they
belong in CI. Pins the blend formula + sort invariants so a future tweak can't
silently degrade every retrieval. Audit 2026-06-23.
"""

import pytest

from app.services.rag_retrieval import _keyword_rerank, _merge_with_alignment_sync


def _r(text_id: int, score: float, chunk_text: str = "", title_zh: str = "", juan: int = 1) -> dict:
    return {
        "text_id": text_id,
        "juan_num": juan,
        "score": score,
        "chunk_text": chunk_text,
        "title_zh": title_zh,
    }


# --- _keyword_rerank --------------------------------------------------------

def test_keyword_rerank_blend_is_70_20_10():
    # vec only: no query-char overlap, no title → score == vec * 0.7
    out = _keyword_rerank("缘起", [_r(1, 1.0, chunk_text="XYZ", title_zh="")])
    assert out[0]["score"] == pytest.approx(0.7)


def test_keyword_rerank_keyword_overlap_weighted_0_2():
    # vec=0, full char overlap (query ⊆ chunk), no title → 0*0.7 + 1.0*0.2 = 0.2
    out = _keyword_rerank("色空", [_r(1, 0.0, chunk_text="色即是空", title_zh="")])
    assert out[0]["score"] == pytest.approx(0.2)


def test_keyword_rerank_title_match_boosts_0_1():
    # vec=0, no chunk overlap, but a 2+char title segment appears in query → +0.1
    out = _keyword_rerank("讲讲心经", [_r(1, 0.0, chunk_text="XYZ", title_zh="心经")])
    assert out[0]["score"] == pytest.approx(0.1)


def test_keyword_rerank_no_title_boost_when_absent_from_query():
    out = _keyword_rerank("缘起性空", [_r(1, 0.0, chunk_text="XYZ", title_zh="心经")])
    assert out[0]["score"] == pytest.approx(0.0)


def test_keyword_rerank_sorts_descending_by_blended_score():
    # Lower vec but title match can overtake a higher-vec, no-match chunk.
    results = [
        _r(1, 0.50, chunk_text="XYZ", title_zh="无关经"),       # 0.35
        _r(2, 0.40, chunk_text="XYZ", title_zh="金刚经"),       # 0.40*0.7 + 0.1 = 0.38
    ]
    out = _keyword_rerank("金刚经讲什么", results)
    assert [r["text_id"] for r in out] == [2, 1]
    assert out[0]["score"] >= out[1]["score"]


# --- _merge_with_alignment_sync ---------------------------------------------

def test_merge_orders_all_three_languages_by_score():
    lzh = [_r(1, 0.9), _r(2, 0.5)]
    pi = [_r(3, 0.7)]
    bo = [_r(4, 0.6)]
    out = _merge_with_alignment_sync(lzh, pi, bo)
    assert [r["text_id"] for r in out] == [1, 3, 4, 2]  # 0.9, 0.7, 0.6, 0.5


def test_merge_empty_inputs():
    assert _merge_with_alignment_sync([], [], []) == []


def test_merge_preserves_all_hits():
    lzh = [_r(1, 0.1), _r(2, 0.2)]
    pi = [_r(3, 0.3)]
    out = _merge_with_alignment_sync(lzh, pi, [])
    assert {r["text_id"] for r in out} == {1, 2, 3}
