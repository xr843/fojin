"""汉字 → 拼音 / SSML，佛教异读以人工词典优先。

读音是「在线读诵」功能的成败点：合成音里读错字，用户听不出来也无从纠正，
比页面上的错字更隐蔽。

为什么不能只靠 pypinyin（均为 2026-08-11 在 T236a 卷1 上实测）：

1. 单字默认读音在佛典中系统性错误。「佛」pypinyin 作 fu2，全卷 123 次
   出现仅 5 次得到 fo2 —— 文言佛典中「佛」大量单用（佛言／爾時佛／白佛言），
   词表补不了，必须有单字默认层。
2. pypinyin 自带的佛教词表只挂在**简体**上。语料是 CBETA 繁体，
   「南無」→ nan2 wu2（简体「南无」→ na1 mo2），等于该词表不存在。

因此词典是两层：词级条目 + 单字默认，统一走最长匹配 —— 单字只是长度为 1
的条目，「仿佛」这类反向保护条目靠更长的匹配自然压过「佛→fo2」。
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from pypinyin import Style, lazy_pinyin

LEXICON_PATH = Path(__file__).with_name("lexicon.tsv")

# CJK 统一表意文字（含扩展 A/B+ 与兼容区）。非汉字（标点、拉丁、空白）不产生音节。
_HAN_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿\U00020000-\U0003ffff]")

_XML_ESCAPES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}


def _escape(text: str) -> str:
    return "".join(_XML_ESCAPES.get(ch, ch) for ch in text)


def _is_han(ch: str) -> bool:
    return bool(_HAN_RE.match(ch))


@lru_cache(maxsize=4)
def load_lexicon(path: Path = LEXICON_PATH) -> dict[str, str]:
    """读词典。返回 {词或字: "空格分隔的带调拼音"}。

    用 lru_cache 是因为流水线会对上千句反复调用；词典只有几百行，常驻无压力。
    """
    entries: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) < 2:
            continue
        word, pinyin = cols[0].strip(), cols[1].strip()
        if word and pinyin:
            entries[word] = pinyin
    return entries


def segment(text: str, lexicon: dict[str, str]) -> list[tuple[str, str | None]]:
    """最长匹配切分。命中给拼音，未命中的连续片段合并后给 None。

    单字条目与词条目在同一张表里，靠「先试长的」自然让「仿佛」压过「佛」。
    """
    if not text:
        return []
    if not lexicon:
        return [(text, None)]

    max_len = max(len(w) for w in lexicon)
    out: list[tuple[str, str | None]] = []
    buf: list[str] = []
    i = 0
    while i < len(text):
        hit: tuple[str, str] | None = None
        for n in range(min(max_len, len(text) - i), 0, -1):
            cand = text[i : i + n]
            if cand in lexicon:
                hit = (cand, lexicon[cand])
                break
        if hit is None:
            buf.append(text[i])
            i += 1
            continue
        if buf:
            out.append(("".join(buf), None))
            buf = []
        out.append(hit)
        i += len(hit[0])
    if buf:
        out.append(("".join(buf), None))
    return out


def to_pinyin(text: str, lexicon: dict[str, str] | None = None) -> str:
    """整段 → 空格分隔的带调拼音（数字调）。

    标点与非汉字不产生音节 —— 供 verify_audio.py 的 whisper-audit 回验做拼音层比对。
    """
    lex = load_lexicon() if lexicon is None else lexicon
    parts: list[str] = []
    for frag, pinyin in segment(text, lex):
        if pinyin is not None:
            parts.append(pinyin)
            continue
        han = "".join(ch for ch in frag if _is_han(ch))
        if han:
            parts.extend(lazy_pinyin(han, style=Style.TONE3, neutral_tone_with_five=True))
    return " ".join(parts)


def to_indextts_syllable(syllable: str) -> str:
    """pypinyin 紧凑形 ``"xu1"`` → IndexTTS 词表形 ``"XV1"``。

    IndexTTS 的 ``checkpoints/pinyin.vocab`` 全大写，且用 ``V`` 表示 ü ——
    它套用了音韵学事实：j/q/x 后拼写作 u 的实际是 ü（「居 jū」实为 /tɕy/）。
    ``y`` **不**适用此规则（词表里是 YU1/YUAN2，不是 YV1）。

    实测（对本仓词典的 104 个音节）：此规则把缺失从 4 个降到 1 个，
    仅 ``NOU4``（耨）确实不在词表内 —— 而 pypinyin 本就把「耨」读对，无需标注。
    """
    m = re.fullmatch(r"([a-z]+)([1-5])", syllable)
    if not m:
        return syllable.upper()
    base, tone = m.groups()
    if base[0] in "jqx" and base[1:2] == "u":
        base = base[0] + "v" + base[2:]
    return base.upper() + tone


def to_indextts_text(
    text: str,
    lexicon: dict[str, str] | None = None,
    vocab: set[str] | None = None,
) -> str:
    """整段 → IndexTTS 2.5 的读音标注格式 ``<字|PINYIN>``。

    官方示例：``他在银<行|XING2>里<行|HANG2>走了半天``。

    ⭐ 与 SSML 的关键差异：角括号形式**保留原字**（SSML 是把原字包在标签里，
    IndexTTS 2.0 的旧式裸替换 ``做DE5`` 则会把原字吃掉）。原字保留意味着
    cue 的字符坐标与 whisper-audit 回验都不受标注影响。

    ``vocab`` 给出时（读自 IndexTTS 的 ``pinyin.vocab``），不在表内的音节
    **不标注**，退回让模型自行判读 —— 标一个模型不认的音节可能整句失效。
    """
    lex = load_lexicon() if lexicon is None else lexicon
    out: list[str] = []
    for frag, pinyin in segment(text, lex):
        if pinyin is None:
            out.append(frag)
            continue
        syllables = pinyin.split()
        if len(frag) != len(syllables) or not all(_is_han(ch) for ch in frag):
            out.append(frag)
            continue
        for ch, syl in zip(frag, syllables, strict=True):
            tagged = to_indextts_syllable(syl)
            out.append(f"<{ch}|{tagged}>" if vocab is None or tagged in vocab else ch)
    return "".join(out)


def load_indextts_vocab(path: Path) -> set[str]:
    """读 IndexTTS 的 ``checkpoints/pinyin.vocab``（每行一个大写音节）。"""
    return {ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()}


def _split_tone(syllable: str) -> tuple[str, str]:
    """``"bo1"`` → ``("bo", "1")``。无调尾按轻声（5）处理。"""
    if syllable and syllable[-1] in "12345":
        return syllable[:-1], syllable[-1]
    return syllable, "5"


def to_ssml(text: str, voice: str, lexicon: dict[str, str] | None = None) -> str:
    """整段 → Azure SSML。词典命中处逐字包 <phoneme>，其余交给厂商前端。

    ⚠️ 格式由微软官方文档核定（speech-ssml-phonetic-sets）：zh-CN 的 sapi
    字母表用**拼音 + 空格 + 声调数字**，且**一个 <phoneme> 只包一个汉字**：

        <phoneme alphabet="sapi" ph="zu 3">组</phoneme>

    不是 ``ph="zu3"``，也不能一个标签包整个词（``ph="bo1 re3"`` 包「般若」）。
    词典内部仍存紧凑形（``"bo1 re3"``），只在生成 SSML 时展开 —— 词典给人看和
    人工审定，紧凑形更易读。

    只包命中片段（而非全文逐字包）：全包会让 TTS 失去词组韵律，读起来像报菜名。
    """
    lex = load_lexicon() if lexicon is None else lexicon
    body: list[str] = []
    for frag, pinyin in segment(text, lex):
        if pinyin is None:
            body.append(_escape(frag))
            continue
        syllables = pinyin.split()
        # 逐字映射的前提是「一字一音节」。对不上就整体放行交给厂商前端 ——
        # 错位地标注读音比不标注更糟。
        if len(frag) != len(syllables) or not all(_is_han(ch) for ch in frag):
            body.append(_escape(frag))
            continue
        for ch, syl in zip(frag, syllables, strict=True):
            base, tone = _split_tone(syl)
            body.append(f'<phoneme alphabet="sapi" ph="{base} {tone}">{_escape(ch)}</phoneme>')
    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        'xml:lang="zh-CN">'
        f'<voice name="{_escape(voice)}">{"".join(body)}</voice>'
        "</speak>"
    )
