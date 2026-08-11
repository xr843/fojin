"""佛教读音层 golden 测试。

读音是「在线读诵」的成败点 —— 合成音里读错字，用户听不出来也纠正不了，
比文字错更隐蔽。本文件把已实测的错读钉成回归用例。

基线（pypinyin 0.55.0，繁体，实测 2026-08-11）：
* 佛 → fu2（应 fo2）。金剛經卷1 中 123 次「佛」只有 5 次读对。
* pypinyin 佛教词表只挂简体，繁体全部走不到。
"""

from pathlib import Path

import pytest

from scripts.audio.g2p import load_lexicon, segment, to_pinyin, to_ssml

LEXICON = load_lexicon()

# (文本, 期望拼音) —— 全部用 CBETA 繁体形
GOLDEN = [
    # ① 单字默认层：pypinyin 单字读音在佛典中系统性错误
    ("佛", "fo2"),
    ("伽", "qie2"),
    ("舍", "she4"),
    ("闍", "she2"),
    # ② 词级层：pypinyin 繁体下读错
    ("般若", "bo1 re3"),
    ("般涅槃", "bo1 nie4 pan2"),
    ("南無", "na1 mo2"),
    ("迦葉", "jia1 she4"),
    ("阿闍世", "a1 she2 shi4"),
    ("闍維", "she2 wei2"),
    ("僧伽", "seng1 qie2"),
    ("瑜伽", "yu2 qie2"),
    ("和南", "he2 na2"),
    ("給孤獨", "ji3 gu1 du2"),
    ("阿鞞跋致", "a1 pi2 ba2 zhi4"),
    ("辟支佛", "bi4 zhi1 fo2"),
    ("薄伽梵", "bo2 qie2 fan4"),
    ("阿蘭若", "a1 lan2 re3"),
    ("伽藍", "qie2 lan2"),
    ("剎那", "cha4 na4"),
    ("兜率", "dou1 shuai4"),
    ("羅剎", "luo2 cha4"),
    ("舍利弗", "she4 li4 fu2"),
    ("舍衛", "she4 wei4"),
    ("王舍城", "wang2 she4 cheng2"),
    # ③ 反向保护：最长匹配必须让「仿佛」压过单字默认 佛→fo2
    ("仿佛", "fang3 fu2"),
    ("彷彿", "pang2 fu2"),
    # ④ 真实句子：单字默认在句中生效
    ("佛告須菩提", "fo2 gao4 xu1 pu2 ti2"),
    ("爾時佛", "er3 shi2 fo2"),
]


@pytest.mark.parametrize(("text", "expected"), GOLDEN)
def test_golden_pronunciation(text: str, expected: str) -> None:
    assert to_pinyin(text, LEXICON) == expected


def test_segment_longest_match_wins() -> None:
    """「仿佛」是词级条目，必须整体命中，不能被单字 佛 拆开。"""
    assert segment("仿佛", LEXICON) == [("仿佛", "fang3 fu2")]


def test_segment_passes_through_unknown_text() -> None:
    """词典未收的片段交回 None，由 pypinyin 兜底。"""
    parts = segment("如是我聞", LEXICON)
    assert all(py is None for _, py in parts)
    assert "".join(frag for frag, _ in parts) == "如是我聞"


def test_punctuation_is_not_pronounced() -> None:
    """标点不产生音节 —— 否则 cue 与音频会整体错位。"""
    assert to_pinyin("佛言：「善哉！」", LEXICON) == "fo2 yan2 shan4 zai1"


def test_to_ssml_wraps_lexicon_hits_only() -> None:
    ssml = to_ssml("佛告須菩提", "zh-CN-YunzeNeural", LEXICON)
    assert '<phoneme alphabet="sapi" ph="fo2">佛</phoneme>' in ssml
    assert "須菩提" in ssml
    assert ssml.startswith("<speak")
    assert 'name="zh-CN-YunzeNeural"' in ssml


def test_to_ssml_escapes_xml() -> None:
    """经文含「」『』等，且 CBETA 校勘串可能带 & < >；未转义会让 SSML 解析失败。"""
    ssml = to_ssml("A<B&C", "zh-CN-YunzeNeural", LEXICON)
    assert "A&lt;B&amp;C" in ssml


def test_lexicon_is_traditional_and_wellformed() -> None:
    """词典自身的完整性：非空、无重复键、拼音格式合法。"""
    path = Path(__file__).resolve().parents[1] / "scripts" / "audio" / "lexicon.tsv"
    seen: set[str] = set()
    rows = 0
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        cols = line.split("\t")
        assert len(cols) >= 2, f"第 {lineno} 行列数不足: {line!r}"
        word, pinyin = cols[0], cols[1]
        assert word not in seen, f"第 {lineno} 行重复键: {word}"
        seen.add(word)
        for syl in pinyin.split():
            assert syl[-1] in "12345", f"第 {lineno} 行 {word} 拼音缺声调: {syl}"
        rows += 1
    assert rows >= 60
