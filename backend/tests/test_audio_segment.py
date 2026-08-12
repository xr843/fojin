"""CBETA 正文分段 —— cue 坐标的产生处。

坐标错了不会报错，只会让高亮整体跳位，所以这里逐条钉死。

两个由使用者实听发现的缺陷已成为回归用例：
* 「唐三藏法師玄奘譯」曾与「觀自在菩薩…」被粘成一句（早期一律 replace("\\n","")）
* 「舍利子！」曾被切成 5 字独立段，合成音在该处突兀加重
"""

from scripts.audio.segment import split_content

# 心經开头的真实结构：标题 / 译者 / 空行 / 正文（含行末折行）
HEART = (
    "般若波羅蜜多心經\n"
    "唐三藏法師玄奘譯\n"
    "\n"
    "觀自在菩薩行深般若波羅蜜多時，照見五\n"
    "蘊皆空，度一切苦厄。\n"
    "\n"
    "「舍利子！色不異空，空不\n"
    "異色，色即是空，空即是色；受、想、行、識，亦復如\n"
    "是。\n"
)


def test_title_and_byline_are_separate_segments() -> None:
    """经名与译者署名各自独立，且不与正文连读。

    使用者实听发现：早期把「玄奘譯」和「觀自在」读成了一句。
    """
    segs = split_content(HEART)
    assert segs[0].kind == "head"
    assert segs[0].text == "般若波羅蜜多心經"
    assert segs[1].kind == "byline"
    assert segs[1].text == "唐三藏法師玄奘譯"
    assert segs[2].kind == "prose"
    assert segs[2].text.startswith("觀自在菩薩")
    # 译者与正文绝不能在同一段
    assert not any("玄奘譯" in s.text and "觀自在" in s.text for s in segs)


def test_line_wrap_inside_a_paragraph_is_removed() -> None:
    """段内单换行是原书行末折行，必须抹掉 —— 否则「五蘊」被拆开。"""
    segs = split_content(HEART)
    prose = next(s for s in segs if s.text.startswith("觀自在"))
    assert "照見五蘊皆空" in prose.text
    assert "\n" not in prose.text


def test_offsets_map_back_to_raw_ignoring_newlines() -> None:
    """坐标不变式：``raw[start:end]`` 抹掉换行后等于 ``text``。

    ⚠️ 不是逐字相等 —— 合并散文行时抹掉了折行，raw 区间里仍含 \\n。
    """
    for s in split_content(HEART):
        assert HEART[s.char_start : s.char_end].replace("\n", "") == s.text


def test_short_sentence_is_merged_not_left_alone() -> None:
    """「舍利子！」不可独立成段 —— 孤立短句会被 TTS 当成强调性话语。"""
    segs = split_content(HEART)
    assert not any(s.text.strip("「") == "舍利子！" for s in segs)
    assert any("舍利子" in s.text and len(s.text) > 16 for s in segs)


def test_ideographic_space_is_preserved() -> None:
    """咒語里的全角空格是分隔符，不能当空白剥掉（会让坐标错位）。"""
    raw = "即說咒曰：\n「揭帝　揭帝　般羅揭帝\n　菩提　莎婆訶」\n"
    segs = split_content(raw)
    joined = "".join(s.text for s in segs)
    assert "　菩提" in joined or "帝　菩提" in joined
    for s in segs:
        assert raw[s.char_start : s.char_end].replace("\n", "") == s.text


def test_segments_do_not_overlap() -> None:
    """区间不可重叠 —— 重叠会让同一段文字被高亮两次。"""
    segs = split_content(HEART)
    for a, b in zip(segs, segs[1:]):
        assert b.char_start >= a.char_end
