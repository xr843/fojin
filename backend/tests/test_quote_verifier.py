"""Tests for quote_verifier.

The verifier's job is to flag quoted passages whose **content** is
fabricated even when the surrounding ``【《X》第N卷】`` reference is
real. Tests therefore exercise both the happy path (quote really is in
chunk_text → no annotation) and the failure shapes the LLM is known to
produce (paraphrase, fabrication, wrong-juan citation).
"""

from app.schemas.chat import ChatSource, ParallelChunk
from app.services.quote_verifier import (
    QuoteMutation,
    _normalise,
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


# ──────────────────────────────────────────────────────────────────────
# Normaliser
# ──────────────────────────────────────────────────────────────────────


def test_normalise_strips_punct_and_whitespace():
    assert _normalise("色不异空，空不异色。") == "色不异空空不异色"


def test_normalise_handles_full_width_quotes_and_brackets():
    assert _normalise("「色不异空」") == "色不异空"
    assert _normalise("『色不异空』") == "色不异空"
    assert _normalise('"色不异空"') == "色不异空"


def test_normalise_nfkc_folds_full_to_half_width():
    """Half-width and full-width digits/letters in the LLM's output
    must compare equal to the canonical text after normalisation."""
    assert _normalise("般若123") == _normalise("般若１２３")


# ──────────────────────────────────────────────────────────────────────
# Verifier — happy paths
# ──────────────────────────────────────────────────────────────────────


def test_pass_through_when_no_citations():
    answer = "般若波罗蜜多。色即是空。"
    out, muts = verify_quoted_content(answer, [_src(1, "心經", 1, "色即是空，空即是色。")])
    assert out == answer
    assert muts == []


def test_quote_in_source_does_not_annotate():
    """A literal quote that appears as a substring of the cited
    chunk_text must pass without annotation. Otherwise we'd
    false-positive on every well-grounded answer."""
    chunk = "色不異空，空不異色，色即是空，空即是色，受想行識亦復如是。"
    src = _src(7, "心經", 1, chunk)
    answer = "经文说：「色不異空，空不異色，色即是空」【《心經》第1卷】"
    out, muts = verify_quoted_content(answer, [src])
    assert out == answer
    assert muts == []


def test_quote_with_extra_punctuation_in_llm_output_still_passes():
    """LLMs often copy a quote with stray full-width commas; the
    normaliser must absorb those without causing a false positive."""
    chunk = "色不異空空不異色色即是空空即是色"  # canonical without punct
    src = _src(7, "心經", 1, chunk)
    answer = '经云："色不異空，空不異色，色即是空。"【《心經》第1卷】'
    out, muts = verify_quoted_content(answer, [src])
    assert out == answer
    assert muts == []


def test_quote_too_short_is_skipped():
    """Quotes below MIN_QUOTE_CHARS are paraphrase-noise prone; the
    verifier deliberately does not flag them."""
    src = _src(7, "心經", 1, "completely different content here")
    answer = "经云：「色即是空」【《心經》第1卷】"
    out, muts = verify_quoted_content(answer, [src])
    assert out == answer
    assert muts == []


# ──────────────────────────────────────────────────────────────────────
# Verifier — failure paths
# ──────────────────────────────────────────────────────────────────────


def test_quote_not_in_source_gets_annotated():
    """The flagship case: LLM cites a real source but the quote
    inside the 「…」 was never in that chunk."""
    src = _src(7, "心經", 1, "实际原文：般若波罗蜜多，照见五蕴皆空。")
    answer = "经文明示：「众生皆有佛性，如来藏不空妙有」【《心經》第1卷】"
    out, muts = verify_quoted_content(answer, [src])
    assert "⚠️" in out
    assert "未在该卷原文中验证到" in out
    assert len(muts) == 1
    assert muts[0].reason == "quote_not_in_source"
    assert muts[0].title == "心經"
    assert muts[0].juan == 1


def test_no_matching_source_gets_annotated_differently():
    """The quote is bound to a citation whose title isn't in sources
    at all (e.g. citation_guard didn't catch it because it was
    title-only). The verifier flags as 'no_matching_source' so the
    audit trail distinguishes 'wrong text' from 'wrong content'."""
    src = _src(7, "心經", 1, "...")
    answer = "云：「众生皆有佛性，如来藏不空妙有」【《不存在经》第1卷】"
    out, muts = verify_quoted_content(answer, [src])
    assert "⚠️" in out
    assert "出处未在检索结果中找到" in out
    assert len(muts) == 1
    assert muts[0].reason == "no_matching_source"


def test_juan_mismatch_falls_back_to_title_match():
    """Source has 心經 juan=1; LLM cites juan=2. If the quote is
    actually in the title's juan=1 chunk, the verifier accepts the
    title-only match — citation_guard handles fascicle correction
    separately, and double-flagging here would noise the user."""
    src = _src(7, "心經", 1, "色不異空空不異色色即是空。")
    answer = "经云：「色不異空空不異色色即是空」【《心經》第2卷】"
    out, muts = verify_quoted_content(answer, [src])
    assert out == answer
    assert muts == []


def test_parallel_chunk_quotes_are_checkable():
    """A Pali parallel arrived via alignment_pairs; if the LLM cites
    the parallel's title and the quote is in the parallel's
    chunk_text, that should pass — parallel sources are legitimate
    targets for citation."""
    src = ChatSource(
        text_id=7, juan_num=1, chunk_index=0, chunk_text="...", score=0.9,
        title_zh="心經", lang="lzh",
        parallel_chunks=[
            ParallelChunk(
                text_id=99, juan_num=2, chunk_index=0,
                chunk_text="evaṃ me sutaṃ ekaṃ samayaṃ bhagavā",
                lang="pi", title="Mahāparinibbāna Sutta",
            )
        ],
    )
    answer = "云：「evaṃ me sutaṃ ekaṃ samayaṃ bhagavā」【《Mahāparinibbāna Sutta》第2卷】"
    out, muts = verify_quoted_content(answer, [src])
    assert out == answer
    assert muts == []


def test_quote_in_non_first_retrieved_chunk_passes():
    """RAG returns several chunks per juan. A quote living in a later
    chunk must still verify — the verifier checks every candidate chunk,
    not just the first-iterated one. Before the multi-chunk fix this
    false-flagged a perfectly legitimate quote."""
    answer = "经中说「以五事交擾，渾濁真性，故名惡世」【《阿彌陀經疏鈔》第4卷】。"
    sources = [
        _src(12379, "阿彌陀經疏鈔", 4, "卷四前段……与引文无关的高分内容……"),
        _src(12379, "阿彌陀經疏鈔", 4, "……以五事交擾，渾濁真性，故名惡世……"),
    ]
    out, muts = verify_quoted_content(answer, sources)
    assert muts == []
    assert "⚠️" not in out


def test_multiple_failing_quotes_all_annotated():
    """Two fabricated quotes in one answer must both be marked, and
    the markers must not interfere with each other (right-to-left
    insertion preserves earlier indices)."""
    src = _src(7, "心經", 1, "无关原文")
    answer = (
        "云：「假引文片段一假引文片段一假引文片段一」【《心經》第1卷】然后："
        "「假引文片段二假引文片段二假引文片段二」【《心經》第1卷】"
    )
    out, muts = verify_quoted_content(answer, [src])
    assert out.count("⚠️") == 2
    assert len(muts) == 2


def test_distant_quote_and_citation_not_treated_as_pair():
    """If a quote is far from the trailing citation (commentary
    paragraph in between), they aren't bound — the verifier
    intentionally under-verifies to avoid over-flagging."""
    src = _src(7, "心經", 1, "无关原文")
    far = " " * 200  # > MAX_QUOTE_CITATION_GAP_CHARS
    answer = f"开始：「假引文一假引文二假引文三」{far}然后【《心經》第1卷】"
    out, muts = verify_quoted_content(answer, [src])
    assert "⚠️" not in out
    assert muts == []


def test_curly_double_quotes_match_quote_pattern():
    """Production sample 2026-05-07: DeepSeek emits typographic curly
    double quotes (U+201C / U+201D) for inline citations, never the
    ASCII " or 「」 forms. The regex must match them or the entire
    module is silent on real production output."""
    src = _src(7, "心經", 1, "无关原文，没有这段引文。")
    answer = "经云：“色不异空，空不异色，色即是空，色即是色”【《心經》第1卷】"
    out, muts = verify_quoted_content(answer, [src])
    assert "⚠️" in out
    assert len(muts) == 1
    assert muts[0].reason == "quote_not_in_source"


def test_markdown_bold_inside_curly_quotes_strips_to_compare_content():
    """Common LLM output: “**色不異空**” — bold markers and
    curly quotes must both be normalised away so the substring check
    sees only the content, otherwise every formatted quote
    false-positives."""
    chunk = "色不異空空不異色色即是空空即是色"
    src = _src(7, "心經", 1, chunk)
    answer = "经云：“**色不異空，空不異色，色即是空，空即是色**”【《心經》第1卷】"
    out, muts = verify_quoted_content(answer, [src])
    assert "⚠️" not in out
    assert muts == []


def test_curly_single_quotes_also_supported():
    src = _src(7, "心經", 1, "实际原文：色即是空空即是色。")
    answer = "经云：‘伪造引文段落很长伪造引文段落很长’【《心經》第1卷】"
    _out, muts = verify_quoted_content(answer, [src])
    assert len(muts) == 1
    assert muts[0].reason == "quote_not_in_source"


def test_returns_dataclass_with_audit_fields():
    """Lock the audit shape so a future migration that persists these
    rows has a stable schema."""
    src = _src(7, "心經", 1, "")
    answer = "云：「假引文假引文假引文假引文」【《心經》第1卷】"
    _, muts = verify_quoted_content(answer, [src])
    assert isinstance(muts[0], QuoteMutation)
    assert muts[0].quote.startswith("假引文")
    assert muts[0].title == "心經"
    assert muts[0].juan == 1
    assert muts[0].reason == "quote_not_in_source"
