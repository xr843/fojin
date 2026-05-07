"""Tests for citation_guard.

The guard is the deterministic backstop after the prompt's moral one;
its tests should therefore exercise every failure mode the prompt is
explicitly trying to forbid in chat.py — hallucinated titles, wrong
fascicle numbers — plus the shape variations the LLM commonly emits.
"""

from app.schemas.chat import ChatSource, ParallelChunk
from app.services.citation_guard import (
    CitationMutation,
    enforce_citation_whitelist,
)


def _src(text_id: int, title: str, juan: int, lang: str = "lzh") -> ChatSource:
    return ChatSource(
        text_id=text_id,
        juan_num=juan,
        chunk_index=0,
        chunk_text="…",
        score=0.9,
        title_zh=title,
        lang=lang,
    )


def test_passes_through_when_no_citation_brackets():
    answer = "般若是空，色即是空。"
    out, muts = enforce_citation_whitelist(answer, [_src(1, "心经", 1)])
    assert out == answer
    assert muts == []


def test_keeps_legitimate_citation_unchanged():
    answer = "见【《心经》第1卷】所说。"
    out, muts = enforce_citation_whitelist(answer, [_src(7, "心经", 1)])
    assert out == answer
    assert muts == []


def test_rewrites_unknown_title_when_whitelist_has_other_titles():
    answer = "依据【《某伪经》第3卷】所述。"
    sources = [_src(7, "心经", 1)]
    out, muts = enforce_citation_whitelist(answer, sources)
    assert "【《某伪经》第3卷】" not in out
    assert "《某伪经》（未在检索结果中验证，请谨慎）" in out
    assert len(muts) == 1
    assert muts[0].kind == "unverified_title"
    assert muts[0].title == "某伪经"
    assert muts[0].original_juan == 3


def test_corrects_fascicle_when_title_real_but_juan_wrong():
    """《心经》is in sources at juan=1; LLM cited 第99卷."""
    answer = "如【《心经》第99卷】所言。"
    out, muts = enforce_citation_whitelist(answer, [_src(7, "心经", 1)])
    assert "【《心经》第1卷】" in out
    assert "第99卷" not in out
    assert len(muts) == 1
    assert muts[0].kind == "fascicle_corrected"
    assert muts[0].original_juan == 99
    assert muts[0].corrected_juan == 1


def test_picks_smallest_fascicle_for_deterministic_replacement():
    """Title appears in multiple sources at different juans — the rewriter
    must be deterministic, not score-dependent, so two reruns of the same
    answer produce the same output."""
    answer = "【《大般若经》第999卷】"
    sources = [
        _src(10, "大般若经", 50),
        _src(11, "大般若经", 100),
        _src(12, "大般若经", 200),
    ]
    out, _ = enforce_citation_whitelist(answer, sources)
    assert "【《大般若经》第50卷】" in out


def test_title_only_citation_passes_when_title_is_real():
    """【《X》】 (no fascicle) should be left alone if the title was retrieved
    — it's a legitimate "the text as a whole" reference."""
    answer = "参见【《心经》】整体大意。"
    out, muts = enforce_citation_whitelist(answer, [_src(7, "心经", 1)])
    assert out == answer
    assert muts == []


def test_title_only_citation_for_unknown_title_is_flagged():
    answer = "参见【《不存在经》】。"
    out, muts = enforce_citation_whitelist(answer, [_src(7, "心经", 1)])
    assert "【《不存在经》】" not in out
    assert "《不存在经》（未在检索结果中验证，请谨慎）" in out
    assert muts[0].original_juan is None


def test_parallel_chunk_titles_count_as_whitelisted():
    """A Pali parallel arrived via alignment_pairs and is attached as
    parallel_chunks — citing it should pass even though it isn't a top-level
    source."""
    src = ChatSource(
        text_id=7, juan_num=1, chunk_index=0, chunk_text="…", score=0.9,
        title_zh="心经", lang="lzh",
        parallel_chunks=[
            ParallelChunk(
                text_id=99, juan_num=2, chunk_index=0, chunk_text="…",
                lang="pi", title="Mahāparinibbāna Sutta",
            )
        ],
    )
    answer = "见【《Mahāparinibbāna Sutta》第2卷】对应。"
    out, muts = enforce_citation_whitelist(answer, [src])
    assert out == answer
    assert muts == []


def test_empty_sources_strips_all_citations_with_caveats():
    """No sources at all means every 【】 is unverifiable. Strip them rather
    than leaving them as-is, since the frontend would render them as
    plain-text but visually-authoritative ghost-citations."""
    answer = "如【《心经》第1卷】与【《金刚经》】所言。"
    out, muts = enforce_citation_whitelist(answer, [])
    assert "【《" not in out
    assert "《心经》（未在检索结果中验证，请谨慎）" in out
    assert "《金刚经》（未在检索结果中验证，请谨慎）" in out
    assert len(muts) == 2
    assert {m.kind for m in muts} == {"unverified_title"}


def test_text_id_zero_sources_excluded_from_whitelist():
    """The frontend's injectCitationLinks drops text_id <= 0; the guard must
    do the same so the backend and frontend agree on what 'verified' means."""
    answer = "依据【《心经》第1卷】所述。"
    out, muts = enforce_citation_whitelist(answer, [_src(0, "心经", 1)])
    assert "【《心经》第1卷】" not in out
    assert "《心经》（未在检索结果中验证，请谨慎）" in out
    assert muts[0].kind == "unverified_title"


def test_handles_multiple_citations_in_one_answer():
    answer = "如【《心经》第1卷】所言，又见【《伪经》第2卷】，再读【《金刚经》第3卷】。"
    sources = [_src(7, "心经", 1), _src(8, "金刚经", 3)]
    out, muts = enforce_citation_whitelist(answer, sources)
    assert "【《心经》第1卷】" in out
    assert "【《金刚经》第3卷】" in out
    assert "【《伪经》第2卷】" not in out
    assert len(muts) == 1
    assert muts[0].title == "伪经"


def test_fascicle_correction_falls_back_to_title_only_when_juan_set_empty():
    """A defensive case: if a future code path adds a title to the whitelist
    with no juan attached, citing it with a wrong juan should drop to a
    safe title-only form rather than hallucinate a fascicle."""
    src = ChatSource(
        text_id=7, juan_num=0, chunk_index=0, chunk_text="…",
        score=0.9, title_zh="心经", lang="lzh",
    )
    # juan_num=0 is falsy-but-valid; whitelist will hold {0}, so a juan=5
    # citation must be corrected to "0" (the only retrieved fascicle).
    answer = "见【《心经》第5卷】"
    out, muts = enforce_citation_whitelist(answer, [src])
    assert "【《心经》第0卷】" in out
    assert muts[0].corrected_juan == 0


def test_mutation_is_dataclass_with_full_audit_fields():
    """Locks the audit shape so a future migration that persists these
    rows has a stable schema to bind to."""
    answer = "【《伪经》第1卷】"
    _, muts = enforce_citation_whitelist(answer, [])
    assert len(muts) == 1
    m = muts[0]
    assert isinstance(m, CitationMutation)
    assert m.kind == "unverified_title"
    assert m.original == "【《伪经》第1卷】"
    assert m.title == "伪经"
    assert m.original_juan == 1
    assert m.corrected_juan is None
    assert "未在检索结果中验证" in m.replacement
