"""佛教读音层 golden 测试。

读音是「在线读诵」的成败点 —— 合成音里读错字，用户听不出来也纠正不了，
比文字错更隐蔽。本文件把已实测的错读钉成回归用例。

基线（pypinyin 0.55.0，繁体，实测 2026-08-11）：
* 佛 → fu2（应 fo2）。金剛經卷1 中 123 次「佛」只有 5 次读对。
* pypinyin 佛教词表只挂简体，繁体全部走不到。
"""

from pathlib import Path

import pytest

from scripts.audio.g2p import (
    load_lexicon,
    segment,
    to_indextts_syllable,
    to_indextts_text,
    to_pinyin,
    to_ssml,
)

LEXICON = load_lexicon()

# (文本, 期望拼音) —— 全部用 CBETA 繁体形
GOLDEN = [
    # ① 单字默认层：pypinyin 单字读音在佛典中系统性错误
    ("佛", "fo2"),
    ("伽", "qie2"),
    ("舍", "she4"),
    ("闍", "she2"),
    ("相", "xiang4"),
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
    # ③ 由 Task 2 读音审计在真实经文上发现（金剛經卷1）
    ("應供", "ying4 gong4"),
    ("調御", "tiao2 yu4"),
    # ③b 由心經合成音**实听**发现 —— 咒語段是词典的盲区，
    #    「般羅揭帝」的「般羅」不是「般若」，原词典匹配不上
    ("般羅", "bo1 luo2"),
    ("般羅揭帝", "bo1 luo2 jie1 di4"),
    ("莎婆訶", "suo1 po2 he1"),
    ("揭帝", "jie1 di4"),  # 心經用「揭帝」，非「揭諦」，两个字形都要收
    # ④ 反向保护：最长匹配必须压过单字默认（佛→fo2、相→xiang4）
    ("仿佛", "fang3 fu2"),
    ("彷彿", "pang2 fu2"),
    ("相應", "xiang1 ying4"),
    ("相續", "xiang1 xu4"),
    ("互相", "hu4 xiang1"),
    # ⑤ 真实句子：单字默认在句中生效
    ("佛告須菩提", "fo2 gao4 xu1 pu2 ti2"),
    ("爾時佛", "er3 shi2 fo2"),
    ("凡所有相，皆是虛妄", "fan2 suo3 you3 xiang4 jie1 shi4 xu1 wang4"),
    ("無我相、無人相", "wu2 wo3 xiang4 wu2 ren2 xiang4"),
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
    # ⚠️ Azure zh-CN sapi 字母表：拼音 + 空格 + 声调数字，一个标签只包一个汉字。
    # 官方文档 speech-ssml-phonetic-sets 的例子是 ph="zu 3" 而非 ph="zu3"。
    assert '<phoneme alphabet="sapi" ph="fo 2">佛</phoneme>' in ssml
    # 須菩提 也在词典里，同样逐字包；「告」未收，原样交给厂商前端
    assert '<phoneme alphabet="sapi" ph="xu 1">須</phoneme>' in ssml
    assert "</phoneme>告<phoneme" in ssml  # 「告」夹在两个标签之间，未被包裹
    assert ssml.count("<phoneme") == 4  # 佛 + 須菩提三字
    assert ssml.startswith("<speak")
    assert 'name="zh-CN-YunzeNeural"' in ssml


def test_to_ssml_emits_one_phoneme_per_character() -> None:
    """多字词必须拆成逐字标签 —— 一个标签包整个词是 Azure 不认的写法。"""
    ssml = to_ssml("般若", "zh-CN-YunzeNeural", LEXICON)
    assert '<phoneme alphabet="sapi" ph="bo 1">般</phoneme>' in ssml
    assert '<phoneme alphabet="sapi" ph="re 3">若</phoneme>' in ssml
    assert ssml.count("<phoneme") == 2
    assert 'ph="bo1 re3"' not in ssml


@pytest.mark.parametrize(
    ("compact", "expected"),
    [
        # j/q/x 后写作 u 的实际是 ü，IndexTTS 词表记作 V
        ("xu1", "XV1"),  # 須（須菩提，金剛經高频）
        ("xun2", "XVN2"),  # 旬（由旬）
        ("ju1", "JV1"),
        ("qu4", "QV4"),
        # y 不适用该规则 —— 词表里是 YU1/YUAN2
        ("yu2", "YU2"),  # 瑜（瑜伽）
        ("yuan2", "YUAN2"),  # 園（祇園）
        # 普通音节直接大写
        ("bo1", "BO1"),
        ("fo2", "FO2"),
        ("re3", "RE3"),
    ],
)
def test_indextts_syllable_conversion(compact: str, expected: str) -> None:
    assert to_indextts_syllable(compact) == expected


def test_indextts_text_keeps_original_characters() -> None:
    """角括号标注必须保留原字 —— cue 坐标与 ASR 回验都依赖原文不被改写。"""
    out = to_indextts_text("佛告須菩提", LEXICON)
    assert out == "<佛|FO2>告<須|XV1><菩|PU2><提|TI2>"
    for ch in "佛告須菩提":
        assert ch in out


def test_indextts_minimal_skips_characters_pypinyin_already_reads_right() -> None:
    """``minimal=True`` 只标 pypinyin 会读错的字（对照实验用，非生产默认）。"""
    out = to_indextts_text("佛告須菩提", LEXICON, minimal=True)
    assert out == "<佛|FO2>告須菩提"
    assert out.count("|") == 1


def test_indextts_minimal_annotates_only_the_wrong_syllable_in_a_word() -> None:
    """词内逐字比对：「給孤獨」只有「給」读错（gěi→jǐ），孤/獨 不标。"""
    assert to_indextts_text("給孤獨園", LEXICON, minimal=True) == "<給|JI3>孤獨園"


def test_indextts_defaults_to_full_annotation() -> None:
    """⚠️ 生产默认必须是全量标注 —— 这是实测结论，别想当然改成最小。

    A/B 实测（2026-08-12，金剛經开经段）音节匹配率：
    全量+放慢 76% / 全量 74% / 最小+放慢 61% / 最小 61% / 无标注 59%。
    最小标注几乎跌回无标注水平 —— 因为「多余」是拿 pypinyin 判的，
    而模型有自己的 G2P，那些标注对它并不多余。
    """
    assert to_indextts_text("給孤獨園", LEXICON).count("|") == 3
    assert to_indextts_text("給孤獨園", LEXICON, minimal=True).count("|") == 1


def test_indextts_text_skips_syllables_outside_vocab() -> None:
    """词表外的音节不标注 —— 标一个模型不认的音节可能让整句失效。"""
    vocab = {"FO2"}  # 只认 FO2
    out = to_indextts_text("佛告須菩提", LEXICON, vocab=vocab)
    assert "<佛|FO2>" in out
    assert "<須|XV1>" not in out  # 不在 vocab，退回裸字
    assert "須" in out


def test_lexicon_syllable_count_matches_char_count() -> None:
    """每条词典的音节数必须等于汉字数，否则逐字映射会静默错位。"""
    from scripts.audio.g2p import _is_han

    for word, pinyin in LEXICON.items():
        n_han = sum(1 for ch in word if _is_han(ch))
        assert n_han == len(word), f"{word} 含非汉字，逐字映射前提不成立"
        assert n_han == len(pinyin.split()), f"{word}: 汉字 {n_han} 个，拼音 {len(pinyin.split())} 个音节"


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
