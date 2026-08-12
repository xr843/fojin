"""把一卷 CBETA 正文切成适合逐句合成的片段 —— cue 坐标的产生处。

⚠️ 两件事必须同时做对，缺一个都会读坏：

1. **两种换行要分开处理**。CBETA 正文里
   * 单 ``\\n`` 是**原书行末折行**（「照見五↵蘊皆空」把「五蘊」拆成两行），
     必须抹掉，否则词被拆开。
   * 空行是**段落边界**，必须保留。
   早期版本一律 ``replace("\\n", "")``，结果「唐三藏法師玄奘譯」和
   「觀自在菩薩…」被粘成一句 —— 使用者一听就发现了。

2. **结构性元素要独立成段**：经名标题、译者署名、卷标题不能与正文连读。
   判定规则**直接港自前端 ``frontend/src/utils/textReflow.ts``**，
   两边同一套行为，不要各写一套。

char_start/char_end 是 ``text_contents.content`` 的 **code-point 偏移**，
与 ``text_apparatus.char_start`` / ``text_line_anchors.char_offset`` 同一坐标系。
"""

from __future__ import annotations

import re
from typing import NamedTuple

# 句末标点：其后断句
_TERMINALS = "。！？；"
# 收尾符号：紧跟句末标点时并入本句
_TRAILERS = "」』）〕】》”’"
# 次级断点：超长句在此二次切分
_SECONDARY = "，、："

_PUNCT = "，。；：！？、"


class Segment(NamedTuple):
    text: str
    char_start: int
    char_end: int
    kind: str  # "head" | "byline" | "juan" | "prose"


def _is_head(line: str, rel_idx: int) -> bool:
    """经名标题，如「般若波羅蜜多心經」。港自 textReflow.ts:97。"""
    if rel_idx > 2 or not (2 <= len(line) <= 15):
        return False
    return bool(re.search(r"[經论論律品序疏記集傳]", line)) and not re.search(f"[{_PUNCT}]", line)


def _is_juan(line: str) -> bool:
    """卷标题，如「大般若波羅蜜多經卷第二」。港自 textReflow.ts:105。"""
    return (
        bool(re.search(r"卷第?[一二三四五六七八九十百千\d]+", line))
        and len(line) <= 25
        and not re.search(r"[，。]", line)
    )


def _is_byline(line: str) -> bool:
    """译者署名，如「唐三藏法師玄奘譯」。港自 textReflow.ts:110。"""
    return (
        bool(re.search(r"[譯译述撰注疏記造]$", line))
        and len(line) <= 25
        and not re.search(r"[，。；]", line)
    )


def _split_prose(
    text: str, offsets: list[int], min_chars: int, max_chars: int
) -> list[Segment]:
    """段内按标点分句；过短的并入下一句，过长的按次级标点二次切分。

    ⚠️ ``min_chars`` 的存在是因为孤立短句会被 TTS 当成强调性话语 ——
    实测心經「舍利子！」被切成 5 字独立段后，合成音在该处突兀加重。
    """
    spans: list[list[int]] = []
    start = i = 0
    n = len(text)
    while i < n:
        if text[i] in _TERMINALS:
            e = i + 1
            while e < n and text[e] in _TRAILERS:
                e += 1
            spans.append([start, e])
            start = e
            i = e
            continue
        i += 1
    if start < n:
        spans.append([start, n])

    # 超长的先二次切分
    split_spans: list[list[int]] = []
    for s, e in spans:
        if e - s <= max_chars:
            split_spans.append([s, e])
            continue
        seg_start = s
        for k in range(s, e):
            if text[k] in _SECONDARY and k - seg_start >= max_chars:
                split_spans.append([seg_start, k + 1])
                seg_start = k + 1
        if seg_start < e:
            split_spans.append([seg_start, e])

    # 再把过短的并进上一段
    merged: list[list[int]] = []
    for s, e in split_spans:
        prev_len = (merged[-1][1] - merged[-1][0]) if merged else 0
        too_short = prev_len < min_chars or (e - s) < min_chars
        if merged and too_short and prev_len + (e - s) <= max_chars:
            merged[-1][1] = e
        else:
            merged.append([s, e])

    # ⚠️ 偏移必须逐字查 offsets[]：合并散文行时抹掉了行末折行，
    #    text 与 raw 不再逐字对应。char_end 取最后一字偏移 +1。
    return [
        Segment(text[s:e], offsets[s], offsets[e - 1] + 1, "prose")
        for s, e in merged
        if text[s:e].strip()
    ]


def split_content(raw: str, min_chars: int = 16, max_chars: int = 60) -> list[Segment]:
    """一卷正文 → 合成片段列表，偏移可切回 ``raw``。

    结构性元素（经名/译者/卷题）各自独立成段，不与正文连读。
    """
    lines = raw.split("\n")
    starts: list[int] = []
    off = 0
    for ln in lines:
        starts.append(off)
        off += len(ln) + 1

    out: list[Segment] = []
    buf_text: list[str] = []
    buf_off: list[int] = []   # 逐字的 raw 偏移，与 buf_text 拼接后等长
    first_nonempty = -1

    def flush() -> None:
        if not buf_text:
            return
        out.extend(_split_prose("".join(buf_text), buf_off, min_chars, max_chars))
        buf_text.clear()
        buf_off.clear()

    # ⚠️ 只剥 ASCII 空白，**不要**剥全角空格 U+3000 —— 咒語里它是有意义的
    #    分隔符（「般羅僧揭帝　菩提　莎婆訶」），剥掉会让坐标与文本对不上。
    ws = " \t\r\n"
    for i, raw_line in enumerate(lines):
        line = raw_line.strip(ws)
        lead = len(raw_line) - len(raw_line.lstrip(ws))
        s = starts[i] + lead
        if not line.strip():
            flush()          # 空行 = 段落边界
            continue
        if first_nonempty < 0:
            first_nonempty = i
        rel = i - first_nonempty

        for pred, kind in ((_is_juan, "juan"), (_is_byline, "byline")):
            if pred(line):
                flush()
                out.append(Segment(line, s, s + len(line), kind))
                break
        else:
            if _is_head(line, rel):
                flush()
                out.append(Segment(line, s, s + len(line), "head"))
            else:
                # 普通散文行：累积待合并（抹掉行末折行），逐字记 raw 偏移
                buf_text.append(line)
                buf_off.extend(range(s, s + len(line)))
    flush()
    return out
