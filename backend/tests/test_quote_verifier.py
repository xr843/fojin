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


def test_quote_not_in_source_is_downgraded_to_prose():
    """The flagship case: LLM cites a real source but the quote inside the 「…」
    was never in that chunk. The verifier now DOWNGRADES it — strips the quote
    marks so it reads as prose — while keeping the citation, and records the
    mutation. fojin never serves the false verbatim claim."""
    src = _src(7, "心經", 1, "实际原文：般若波罗蜜多，照见五蕴皆空。")
    answer = "经文明示：「众生皆有佛性，如来藏不空妙有」【《心經》第1卷】"
    out, muts = verify_quoted_content(answer, [src])
    assert "⚠️" not in out
    assert "「" not in out and "」" not in out          # marks stripped
    assert "众生皆有佛性，如来藏不空妙有" in out          # text kept as prose
    assert "【《心經》第1卷】" in out                     # citation preserved
    assert len(muts) == 1
    assert muts[0].reason == "quote_not_in_source"
    assert muts[0].title == "心經"
    assert muts[0].juan == 1


def test_no_matching_source_is_downgraded():
    """The quote is bound to a citation whose title isn't in sources at all.
    Still downgraded; the audit mutation keeps the 'wrong text' distinction."""
    src = _src(7, "心經", 1, "...")
    answer = "云：「众生皆有佛性，如来藏不空妙有」【《不存在经》第1卷】"
    out, muts = verify_quoted_content(answer, [src])
    assert "「" not in out                               # marks stripped
    assert "众生皆有佛性，如来藏不空妙有" in out
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


def test_simplified_answer_quote_verifies_against_traditional_source():
    """The user asks in 简体; the LLM answers and cites in 简体; CBETA stores
    繁体. A faithful simplified rendering of the traditional original must
    verify — script localisation is not a fidelity loss, and before the
    繁→简 fold every such quote drowned the answer in false ⚠️ notices."""
    answer = "经云「一切诸行皆是无常，是名第一」【《瑜伽师地论》第46卷】。"
    # CBETA-style source: traditional title AND traditional chunk text.
    src = _src(7, "瑜伽師地論", 46, "如彼頌言「一切諸行皆是無常，是名第一」唱拕南。")
    out, muts = verify_quoted_content(answer, [src])
    assert muts == []
    assert "⚠️" not in out


def test_multiple_failing_quotes_are_all_downgraded():
    """Two fabricated quotes in one answer are both downgraded (marks stripped)
    and both logged."""
    src = _src(7, "心經", 1, "无关原文")
    answer = (
        "云：「假引文片段一假引文片段一假引文片段一」【《心經》第1卷】然后："
        "「假引文片段二假引文片段二假引文片段二」【《心經》第1卷】"
    )
    out, muts = verify_quoted_content(answer, [src])
    assert "「" not in out and "」" not in out           # both downgraded
    assert "假引文片段一假引文片段一假引文片段一" in out
    assert "假引文片段二假引文片段二假引文片段二" in out
    assert len(muts) == 2


def test_downgrade_leaves_followup_block_intact():
    """Downgrading an inline fab must not disturb a trailing [追问] block."""
    src = _src(7, "心經", 1, "无关原文")
    answer = (
        "云：「假引文片段一假引文片段一假引文片段一」【《心經》第1卷】\n"
        "[追问] 问题一\n"
        "[追问] 问题二\n"
    )
    out, muts = verify_quoted_content(answer, [src])
    assert len(muts) == 1
    assert "「" not in out                               # downgraded
    assert "[追问] 问题一" in out and "[追问] 问题二" in out


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
    assert "“" not in out and "”" not in out            # curly marks stripped
    assert "色不异空，空不异色" in out
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


# ──────────────────────────────────────────────────────────────────────
# Verifier — Markdown blockquote mode
# ──────────────────────────────────────────────────────────────────────
#
# LLMs frequently format long quotations as Markdown blockquotes:
#
#     > 色不異空，空不異色，
#     > 色即是空，空即是色。
#     >
#     > —— 【《心經》第1卷】
#
# The inline-quote scanner above cannot see these because the body is
# never wrapped in 「」/“”/'' and may span multiple lines. The block
# below exercises a dedicated multi-line scanner that pairs a contiguous
# `> …` block with a nearby `【《X》第N卷】` citation, with the same
# substring-test semantics as the inline path.


def test_blockquote_quote_in_source_does_not_annotate():
    """The happy path: a multi-line `> …` block whose stripped content
    appears verbatim in the cited chunk_text must not annotate."""
    chunk = "色不異空，空不異色，色即是空，空即是色，受想行識亦復如是。"
    src = _src(7, "心經", 1, chunk)
    answer = (
        "经云：\n\n"
        "> 色不異空，空不異色，\n"
        "> 色即是空，空即是色\n\n"
        "【《心經》第1卷】"
    )
    out, muts = verify_quoted_content(answer, [src])
    assert out == answer
    assert muts == []


def test_blockquote_not_in_source_is_downgraded():
    """LLM fabricates a blockquote passage and pairs it with a real title.
    The `> ` markers are stripped so it becomes prose; the citation stays."""
    src = _src(7, "心經", 1, "实际原文：般若波罗蜜多，照见五蕴皆空。")
    answer = (
        "经文明示：\n\n"
        "> 众生皆有佛性，如来藏不空妙有，\n"
        "> 此乃如来真实义\n\n"
        "【《心經》第1卷】"
    )
    out, muts = verify_quoted_content(answer, [src])
    assert "⚠️" not in out
    assert "> 众生皆有佛性" not in out                   # blockquote markers stripped
    assert "众生皆有佛性，如来藏不空妙有" in out          # text kept as prose
    assert "【《心經》第1卷】" in out
    assert len(muts) == 1
    assert muts[0].reason == "blockquote_not_in_source"
    assert muts[0].title == "心經"
    assert muts[0].juan == 1


def test_blockquote_simplified_quote_verifies_against_traditional_source():
    """Same 繁→简 fold semantics as the inline path — a simplified
    blockquote rendering of a traditional CBETA source must pass."""
    src = _src(7, "瑜伽師地論", 46, "如彼頌言「一切諸行皆是無常，是名第一」唱拕南。")
    answer = (
        "经云：\n\n"
        "> 一切诸行皆是无常，是名第一\n\n"
        "【《瑜伽师地论》第46卷】"
    )
    out, muts = verify_quoted_content(answer, [src])
    assert out == answer
    assert muts == []


def test_blockquote_with_citation_on_trailing_blockquote_line():
    """Common LLM style: citation lives on a final `> ——【《X》第N卷】`
    line inside the same blockquote block. Must still pair."""
    src = _src(7, "心經", 1, "色不異空空不異色色即是空空即是色。")
    answer = (
        "> 色不異空，空不異色，色即是空，空即是色\n"
        "> ——【《心經》第1卷】"
    )
    out, muts = verify_quoted_content(answer, [src])
    assert out == answer
    assert muts == []


def test_blockquote_too_short_is_skipped():
    """Blockquote whose stripped content is < MIN_QUOTE_CHARS gets the
    same paraphrase-noise treatment as inline short quotes — skipped."""
    src = _src(7, "心經", 1, "completely different content here")
    answer = "经云：\n\n> 色即是空\n\n【《心經》第1卷】"
    out, muts = verify_quoted_content(answer, [src])
    assert out == answer
    assert muts == []


def test_blockquote_far_from_citation_not_treated_as_pair():
    """Same gap-window discipline as the inline path: a blockquote
    separated from the citation by several paragraphs of commentary is
    not bound to it and the verifier under-verifies rather than
    misattributes."""
    src = _src(7, "心經", 1, "无关原文")
    answer = (
        "> 假引文一假引文二假引文三假引文四\n\n"
        "中间穿插一段无关紧要的注释解说文字。" * 8
        + "\n\n【《心經》第1卷】"
    )
    out, muts = verify_quoted_content(answer, [src])
    assert "⚠️" not in out
    assert muts == []


def test_downgrade_is_idempotent():
    """A downgraded passage carries no quote marks, so a second pass over the
    corrected answer is a no-op and reports no further mutations — the served
    answer is already clean."""
    src = _src(7, "心經", 1, "实际原文：般若波罗蜜多。")
    answer = (
        "经云：\n\n"
        "> 众生皆有佛性，如来藏不空妙有，此真实义\n\n"
        "【《心經》第1卷】"
    )
    out, muts = verify_quoted_content(answer, [src])
    assert len(muts) == 1
    out2, muts2 = verify_quoted_content(out, [src])
    assert out2 == out       # no further change
    assert muts2 == []       # nothing left to downgrade


def test_blockquote_and_inline_failures_both_downgraded():
    """Mixed failure modes (one inline 「…」 fab + one `> …` fab) are both
    downgraded, both recorded in the audit list."""
    src = _src(7, "心經", 1, "无关原文")
    answer = (
        "云：「假引文片段一假引文片段一假引文片段一」【《心經》第1卷】\n\n"
        "又云：\n\n"
        "> 假引文片段二假引文片段二假引文片段二\n\n"
        "【《心經》第1卷】"
    )
    out, muts = verify_quoted_content(answer, [src])
    assert "「" not in out and "> 假引文片段二" not in out   # both downgraded
    assert "假引文片段一假引文片段一假引文片段一" in out
    assert "假引文片段二假引文片段二假引文片段二" in out
    assert len(muts) == 2
    reasons = {m.reason for m in muts}
    assert reasons == {"quote_not_in_source", "blockquote_not_in_source"}


# ──────────────────────────────────────────────────────────────────────
# Over-capture: 「」 as CJK emphasis, not quotation
#
# Prod evidence (chat_answer_diagnostics, 2026-07-09): of 75 quotes the
# verifier bucketed ``absent``, 69% contained a newline, 45% contained
# markdown bold, mean length 145 chars — while the 3 ``near_miss`` (real)
# quotes averaged 36 chars with no newlines. The inline regex was walking
# past nested marks and across paragraphs to reach any citation within the
# gap window, so ordinary emphasis got downgraded as a fabricated quote.
# ──────────────────────────────────────────────────────────────────────


def test_emphasis_marks_are_not_extracted_as_a_quote():
    """CJK 「」 used for emphasis must not be captured as a quotation.

    The passage below quotes nothing verbatim; every 「…」 is emphasis and
    each is shorter than MIN_QUOTE_CHARS. Nothing should be downgraded, and
    the served answer must keep its emphasis marks intact."""
    src = _src(3, "瑜伽師地論", 3, "必与舍受相应，能持寻伺。")
    answer = (
        "「念」的功能正是维持、把持这种「寻」，如果伴随苦乐，寻就会波动。\n\n"
        "逐句消文：\n"
        "- **「第二依地门」**：这是论中分析此种心所的第二门。\n"
        "- 论中说必与舍受相应【《瑜伽師地論》第3卷】。\n"
    )
    out, muts = verify_quoted_content(answer, [src])
    assert muts == []
    assert out == answer
    assert "「念」" in out and "「寻」" in out


def test_quote_capture_stops_at_the_first_closing_mark():
    """A quote must not swallow a later 「…」 pair to reach a citation."""
    src = _src(3, "瑜伽師地論", 3, "无关原文")
    answer = "「甲」中间夹了很多很多很多的散文字句「乙」【《瑜伽師地論》第3卷】"
    out, muts = verify_quoted_content(answer, [src])
    assert muts == []
    assert out == answer


def test_quote_does_not_span_a_newline():
    """An inline quote is a single-line construct; blockquotes have their own
    scanner. A 「 that never closes on its line must not capture across lines."""
    src = _src(7, "心經", 1, "无关原文")
    answer = "开头出现一个孤立的「引号但这一行没有闭合\n下一行才闭合了引号」【《心經》第1卷】"
    out, muts = verify_quoted_content(answer, [src])
    assert muts == []
    assert out == answer


def test_mismatched_open_and_close_marks_do_not_pair():
    """「 must be closed by 」 — not by ” or a straight quote."""
    src = _src(7, "心經", 1, "无关原文")
    answer = '云：「这是一段足够长的假引文内容啊”【《心經》第1卷】'
    out, muts = verify_quoted_content(answer, [src])
    assert muts == []
    assert out == answer


def test_real_paraphrase_as_quote_is_still_downgraded():
    """Regression guard: the actual feature must survive the precision fix."""
    src = _src(7, "心經", 1, "五陰覆蓋，使昏迷故。")
    answer = "论云：「五阴覆盖般若灵明，使众生心识昏蒙」【《心經》第1卷】"
    out, muts = verify_quoted_content(answer, [src])
    assert len(muts) == 1
    assert "「" not in out
    assert "五阴覆盖般若灵明，使众生心识昏蒙" in out


def test_real_verbatim_quote_still_verifies():
    """Regression guard: a genuine verbatim quote is left alone."""
    src = _src(7, "心經", 1, "舍利子，色不异空，空不异色，色即是空。")
    answer = "经云：「色不异空，空不异色，色即是空」【《心經》第1卷】"
    out, muts = verify_quoted_content(answer, [src])
    assert muts == []
    assert out == answer


def test_quote_does_not_bind_to_a_citation_across_paragraphs():
    """The gap window is 80 chars of *the same line*, per the module docstring:
    a quote separated from the citation by commentary isn't attributable to it."""
    src = _src(7, "心經", 1, "无关原文")
    answer = (
        "论中说：「一段足够长的十二字以上引文」，此处先不展开。\n\n"
        "下面这段解说与上文无关【《心經》第1卷】"
    )
    out, muts = verify_quoted_content(answer, [src])
    assert muts == []
    assert out == answer


def test_english_quote_with_typographic_apostrophe_is_still_checked():
    """U+2019 doubles as a closing single quote *and* an English apostrophe.
    Excluding it from every quote body would silently stop verifying English
    quotes (84000 / SuttaCentral translations), trading over-capture for
    under-verification. Only the mark that *pairs* with the opener may end it."""
    src = _src(9, "Dhammapada", 1, "Unrelated canonical text.")
    answer = '“the Buddha’s own words, plainly stated”【《Dhammapada》第1卷】'
    _, muts = verify_quoted_content(answer, [src])
    assert len(muts) == 1
    assert muts[0].quote == "the Buddha’s own words, plainly stated"
