"""Tests for the failed-quote bucket classifier (measurement only).

``verify_quoted_content`` downgrades any 「」/blockquote quote that isn't a
verbatim substring of the cited chunk. That flat "unverified" signal conflates
two very different failure modes:

  * a genuinely correct canonical quote whose source chunk the retriever simply
    didn't surface (or that differs by a variant char / edition) — a
    *measurement artifact*, wrongly stripped by the downgrade; vs.
  * a paraphrase or fabrication that is nowhere near the source — the real
    problem.

Each ``QuoteMutation`` now carries ``similarity`` + ``bucket``
("near_miss" / "absent") so the two can be told apart. These tests pin that
classification and confirm the served answer is byte-identical to before.
"""

import logging

from app.schemas.chat import ChatSource
from app.services.quote_verifier import (
    NEAR_MISS_THRESHOLD,
    QuoteMutation,
    verify_quoted_content,
)


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


# The canonical passage used as the retrieved source across tests.
_HEART = "色不異空空不異色色即是空空即是色受想行識亦復如是"


# ──────────────────────────────────────────────────────────────────────
# near_miss: almost-verbatim quote wrongly downgraded
# ──────────────────────────────────────────────────────────────────────


def test_near_miss_when_quote_almost_matches_source():
    """A quote identical to the source but for one trailing character fails
    the exact-substring test yet is ~verbatim — it must bucket as near_miss
    (the downgrade is likely stripping a correct quote)."""
    src = _src(1, "心經", 1, _HEART)
    # Same as the source's opening but with an extra 「也」 the chunk lacks.
    answer = "经文说「色不異空空不異色色即是空空即是色也」【《心經》第1卷】"
    _out, muts = verify_quoted_content(answer, [src])

    assert len(muts) == 1
    assert muts[0].reason == "quote_not_in_source"
    assert muts[0].bucket == "near_miss"
    assert muts[0].similarity >= NEAR_MISS_THRESHOLD


# ──────────────────────────────────────────────────────────────────────
# absent: paraphrase / fabrication
# ──────────────────────────────────────────────────────────────────────


def test_absent_when_quote_is_a_paraphrase():
    """A modern-language paraphrase shares almost nothing with the source
    verbatim — it must bucket as absent with low similarity."""
    src = _src(1, "心經", 1, _HEART)
    answer = "经文大意是「這段話闡述諸法本無自性的空性道理」【《心經》第1卷】"
    _out, muts = verify_quoted_content(answer, [src])

    assert len(muts) == 1
    assert muts[0].reason == "quote_not_in_source"
    assert muts[0].bucket == "absent"
    assert muts[0].similarity < NEAR_MISS_THRESHOLD


def test_absent_when_no_matching_source():
    """A quote cited to a title absent from the retrieved set has no candidate
    chunk to compare against — similarity 0.0, bucket absent."""
    src = _src(1, "心經", 1, _HEART)
    # Cited to a sutra that was never retrieved.
    answer = "论中说「這是一段並不存在於檢索結果中的長引文內容」【《楞嚴經》第3卷】"
    _out, muts = verify_quoted_content(answer, [src])

    assert len(muts) == 1
    assert muts[0].reason == "no_matching_source"
    assert muts[0].bucket == "absent"
    assert muts[0].similarity == 0.0


# ──────────────────────────────────────────────────────────────────────
# verified quotes never produce a mutation (bucket path never runs)
# ──────────────────────────────────────────────────────────────────────


def test_exact_quote_produces_no_mutation():
    src = _src(1, "心經", 1, _HEART)
    answer = "经文说「色不異空空不異色色即是空」【《心經》第1卷】"
    out, muts = verify_quoted_content(answer, [src])

    assert muts == []
    assert out == answer


# ──────────────────────────────────────────────────────────────────────
# summary log + answer-unchanged guarantee
# ──────────────────────────────────────────────────────────────────────


def test_summary_log_reports_bucket_counts(caplog):
    """One near_miss + one absent in the same answer → a single structured
    summary line with per-bucket counts."""
    src = _src(1, "心經", 1, _HEART)
    answer = (
        "一「色不異空空不異色色即是空空即是色也」【《心經》第1卷】"
        "二「這段話闡述諸法本無自性的空性道理」【《心經》第1卷】"
    )
    with caplog.at_level(logging.INFO, logger="app.services.quote_verifier"):
        _out, muts = verify_quoted_content(answer, [src])

    buckets = sorted(m.bucket for m in muts)
    assert buckets == ["absent", "near_miss"]
    assert "quote_verify buckets: near_miss=1 absent=1 total_failed=2" in caplog.text


def test_bucketing_does_not_change_served_answer():
    """Instrumentation only: the corrected answer for a failing quote must be
    exactly the downgraded prose (quote marks stripped), unaffected by the new
    similarity/bucket fields."""
    src = _src(1, "心經", 1, _HEART)
    answer = "经文说「這段話闡述諸法本無自性的空性道理」【《心經》第1卷】"
    out, _muts = verify_quoted_content(answer, [src])

    # Marks dropped, text + citation preserved (the pre-instrumentation shape).
    assert "「" not in out and "」" not in out
    assert "這段話闡述諸法本無自性的空性道理" in out
    assert "【《心經》第1卷】" in out


def test_default_similarity_and_bucket_are_backward_compatible():
    """Existing construction sites / callers that don't pass the new fields
    still work, with conservative defaults."""
    m = QuoteMutation(quote="x" * 12, title="心經", juan=1, reason="quote_not_in_source")
    assert m.similarity == 0.0
    assert m.bucket == "absent"
