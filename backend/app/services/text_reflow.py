"""Reflow CBETA hard-wrapped source text into layout segments.

A faithful Python port of the frontend ``reflowText`` (TextReaderPage.tsx) so
that exported HTML/EPUB/DOCX match the web reader's typography instead of the
raw one-line-per-source-line layout. Offsets are dropped (exports place no
inline apparatus markers), which keeps this a plain string transform.

Segment types mirror the frontend: prose / verse / break / head / juan /
byline / section.

Known parity caveat: length comparisons use ``len()`` (code points) while the
JS source uses ``.length`` (UTF-16 units). These differ only for
supplementary-plane glyphs (e.g. CJK Ext-B, U+20000+) sitting exactly on a
length threshold — rare enough that we accept the divergence rather than thread
UTF-16 width everywhere. ASCII-digit parity (``\d`` → ``0-9``) IS handled, since
fullwidth digits in juan/section titles are comparatively common.
"""

import re
from dataclasses import dataclass

_SENTENCE_END = re.compile(r"[。！？」』]$")
_VERSE_MARKER = re.compile(r"頌曰[：:]?|偈曰[：:]?")
_PROSE_MARKER = re.compile(r"^(論曰|述曰|疏曰|解曰|釋曰)")
_ALL_PUNCT = re.compile(r"[，。、；：！？]")
_VERSE_END = re.compile(r"[，。；]$")
_WS_GAP = re.compile(r"\s{2,}")


@dataclass
class Segment:
    type: str  # prose | verse | break | head | juan | byline | section
    text: str = ""


def _is_verse(line: str) -> bool:
    n = len(line)
    if n < 4 or n > 22:
        return False
    if not _VERSE_END.search(line):
        return False
    all_puncts = len(_ALL_PUNCT.findall(line))
    if all_puncts > 2:
        return False
    if _WS_GAP.search(line):
        return True
    if all_puncts == 2:
        parts = re.split(r"[，。、；]", line)
        if len(parts) >= 2 and len(parts[0]) > 0 and len(parts[1]) > 0:
            ratio = min(len(parts[0]), len(parts[1])) / max(len(parts[0]), len(parts[1]))
            return ratio >= 0.5
    return all_puncts == 1 and n <= 12


def _is_head(line: str, idx: int) -> bool:
    if idx > 2:
        return False
    if len(line) > 15 or len(line) < 2:
        return False
    return bool(re.search(r"[經论論律品序疏記集傳]", line)) and not re.search(r"[，。；：！？、]", line)


def _is_juan(line: str) -> bool:
    # \d → 0-9 (ASCII only): mirror JS RegExp \d, which — unlike Python's
    # Unicode \d — does not match fullwidth digits. Keeps parity with the reader.
    return bool(re.search(r"卷第?[一二三四五六七八九十百千0-9]+", line)) and len(line) <= 25 and not re.search(r"[，。]", line)


def _is_byline(line: str) -> bool:
    return bool(re.search(r"[譯译述撰注疏記造]$", line)) and len(line) <= 25 and not re.search(r"[，。；]", line)


def _is_section(line: str) -> bool:
    # \d → 0-9 (ASCII only) to mirror JS RegExp \d — see _is_juan.
    if re.match(r"^[（(][一二三四五六七八九十0-9]+[）)]", line):
        return True
    return bool(re.search(r"[品分經]第[一二三四五六七八九十百0-9]+", line)) and len(line) <= 20 and not re.search(r"[，。]", line)


def reflow(raw: str) -> list[Segment]:
    lines = raw.split("\n")
    segments: list[Segment] = []
    prose_buf = ""

    def flush_prose() -> None:
        nonlocal prose_buf
        if prose_buf:
            segments.append(Segment("prose", prose_buf))
            prose_buf = ""

    in_verse_block = False
    before_first_prose = True
    first_nonempty_idx = -1
    last_nonempty_line = ""

    for i, rawline in enumerate(lines):
        trimmed = rawline.strip()

        if trimmed == "":
            if _SENTENCE_END.search(last_nonempty_line):
                flush_prose()
                segments.append(Segment("break"))
            continue

        last_nonempty_line = trimmed
        if first_nonempty_idx < 0:
            first_nonempty_idx = i
        rel_idx = i - first_nonempty_idx

        if _is_juan(trimmed):
            flush_prose()
            segments.append(Segment("juan", trimmed))
            continue
        if _is_byline(trimmed):
            flush_prose()
            segments.append(Segment("byline", trimmed))
            continue
        if _is_section(trimmed):
            flush_prose()
            segments.append(Segment("section", trimmed))
            continue
        if _is_head(trimmed, rel_idx):
            flush_prose()
            segments.append(Segment("head", trimmed))
            continue

        has_verse_marker = bool(_VERSE_MARKER.search(trimmed))
        is_prose_marker = bool(_PROSE_MARKER.search(trimmed))

        if is_prose_marker:
            before_first_prose = False
            in_verse_block = False
            if prose_buf:
                flush_prose()
            prose_buf = trimmed
            continue

        if has_verse_marker:
            before_first_prose = False
            prose_buf += trimmed
            flush_prose()
            in_verse_block = True
            continue

        if (in_verse_block or before_first_prose) and _is_verse(trimmed):
            flush_prose()
            segments.append(Segment("verse", trimmed))
            continue

        if in_verse_block and not _is_verse(trimmed):
            in_verse_block = False
        if before_first_prose and not _is_verse(trimmed):
            before_first_prose = False

        prose_buf += trimmed

    flush_prose()
    return segments
