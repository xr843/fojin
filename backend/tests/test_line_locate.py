"""Line-level links for verified quotes: find where in the fascicle a quote
sits, then the CBETA line it starts on (user feedback 2026-11-22: 「点击查看原文
后，如果能直接定位到所查的那句，就方便啦」)."""

from app.services.line_locate import locate_offset, locate_span, nearest_line

CONTENT = "從此第三，明忍智次第。\n釋曰：忍是無間道，約斷惑得，不被惑得之所隔礙，故名無間。智是解脫道。"


def test_simplified_quote_maps_back_to_its_offset_in_the_traditional_text():
    at = locate_offset(CONTENT, "忍是无间道，约断惑得，不被惑得之所隔碍，故名无间。")
    assert at is not None
    assert CONTENT[at:].startswith("忍是無間道")


def test_punctuation_and_line_breaks_do_not_matter():
    assert locate_offset("如夢、幻、\n泡、影", "如梦幻泡影") == 0


def test_variant_spellings_fold_like_the_verifier():
    at = locate_offset("觀自在菩薩。心無罣礙，無罣礙故", "心无挂碍，无挂碍故")
    assert at == 6


def test_absent_quote_has_no_offset():
    assert locate_offset(CONTENT, "一切都是最好的安排") is None


def test_nearest_line_is_the_last_marker_at_or_before_the_offset():
    anchors = [(0, "0947a14"), (11, "0947a15"), (20, "0947a16")]
    assert nearest_line(anchors, 0) == "0947a14"
    assert nearest_line(anchors, 19) == "0947a15"
    assert nearest_line(anchors, 20) == "0947a16"
    assert nearest_line([], 5) is None


def test_span_covers_the_whole_quote_with_its_inner_punctuation():
    first, last = locate_span(CONTENT, "忍是无间道，约断惑得，不被惑得之所隔碍，故名无间")
    assert CONTENT[first : last + 1] == "忍是無間道，約斷惑得，不被惑得之所隔礙，故名無間"


def test_span_starts_mid_line_not_at_the_line_start():
    # 「如是我聞：一時……」: the quote starts at 一時, not at the line's 如是我聞
    content = "如是我聞：一時，婆伽婆一切智人，在王舍城"
    first, last = locate_span(content, "一时，婆伽婆一切智人")
    assert content[first : last + 1] == "一時，婆伽婆一切智人"


# 2026-11-22 用户截图：查「……演說甚深根聚法門。」，阅读器高亮停在「法門」，句号露在外面。
def test_span_takes_in_the_sources_closing_punctuation_when_the_quote_ends_with_one():
    content = "如是我聞：一時，婆伽婆一切智人，演說甚深根聚法門。爾時，會中"
    first, last = locate_span(content, "一時，婆伽婆一切智人，演說甚深根聚法門。")
    assert content[first : last + 1] == "一時，婆伽婆一切智人，演說甚深根聚法門。"


def test_closing_quote_marks_after_the_full_stop_are_taken_too():
    content = "佛言：「善男子！隨汝所問，便可說之。」堅淨信"
    first, last = locate_span(content, "「隨汝所問，便可說之。」")
    assert content[first : last + 1] == "隨汝所問，便可說之。」"


def test_opening_quote_mark_is_taken_when_the_quote_starts_with_one():
    content = "佛言：「善男子！隨汝所問。」"
    first, last = locate_span(content, "「善男子！")
    assert content[first : last + 1] == "「善男子！"


def test_no_trailing_punctuation_in_the_quote_means_no_extension():
    # clause-level checks send bare text; the highlight must not grow past it
    content = "演說甚深根聚法門。爾時"
    first, last = locate_span(content, "演說甚深根聚法門")
    assert content[first : last + 1] == "演說甚深根聚法門"


# 2026-11-22 用户截图：「何謂對法？」定位到了前一句「其論者何？謂對法藏」里——去掉标点后
# 「者何謂對法藏」恰好含这四个字。一句话出现多次时，取前后都挨着标点的那一处。
def test_prefers_the_occurrence_that_starts_and_ends_on_punctuation():
    content = "其論者何？謂對法藏。何謂對法？頌曰："
    first, last = locate_span(content, "何謂對法？")
    assert content[first : last + 1] == "何謂對法？"
    assert first == content.index("。何謂") + 1


def test_falls_back_to_the_first_occurrence_without_a_clean_one():
    content = "者何謂對法藏"
    first, last = locate_span(content, "何謂對法")
    assert content[first : last + 1] == "何謂對法"
