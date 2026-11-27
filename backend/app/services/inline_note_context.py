"""给检索到的段落附上夹注（CBETA 双行小注），只用于交给模型的上下文。

text_embeddings.chunk_text 与 text_contents.content 一样不含夹注（夹注另存 text_inline_notes）。
注疏里夹注常是作者自己的释文（楞严经疏解蒙钞 57% 的文字在夹注里），模型只看正文等于读一半。

做法：在本卷正文里找到这一段（不计换行——检索段落与正文的硬换行位置常不同，实测 300 段 92% 找得到），
把落在段内的夹注按位置以「（…）」插回，与阅读页的显示一致。找不到就原样返回。
chunk_text 本身不改：引文核对仍以不含夹注的正文为准。

线上默认关闭（settings.rag_inline_notes），先经 eval/notes_pair_eval.py 配对评测。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.text import TextContent, TextInlineNote

# 一段最多附多少字夹注（相对正文长度）：音义一类夹注是正文的数倍，不加上限会挤掉别的段落
MAX_NOTE_RATIO = 1.0


def _flat_index(s: str) -> tuple[str, list[int]]:
    keep = [i for i, ch in enumerate(s) if ch != "\n"]
    return "".join(s[i] for i in keep), keep


def splice_notes(chunk: str, content: str, notes: list[tuple[int, str]]) -> str | None:
    """把落在这一段里的夹注插回段落文字。notes：(在 content 中的位置, 夹注文字)，按原文顺序。
    返回插好夹注的段落；这一段在正文里找不到（或找到不止一处）、或段内没有夹注时返回 None。"""
    flat_content, cmap = _flat_index(content)
    flat_chunk, kmap = _flat_index(chunk)
    if not flat_chunk:
        return None
    at = flat_content.find(flat_chunk)
    if at < 0 or flat_content.find(flat_chunk, at + 1) >= 0:
        return None
    # 段内第 k 个非换行字 ↔ 正文位置 cmap[at+k]
    start = cmap[at]
    end = cmap[at + len(flat_chunk) - 1] + 1
    # 正文位置 → 段内「插在第几个非换行字之后」
    pos_of = {cmap[at + k]: k for k in range(len(flat_chunk))}
    budget = int(len(flat_chunk) * MAX_NOTE_RATIO)
    inserts: dict[int, list[str]] = {}
    used = 0
    for off, text in notes:
        if not (start < off <= end):  # 夹注跟在 off-1 那个字后面；off-1 须在段内
            continue
        k = pos_of.get(off - 1)
        if k is None:
            continue
        if used >= budget:
            inserts.setdefault(k, []).append("（……）")
            break
        piece = text if used + len(text) <= budget else text[: budget - used] + "……"
        used += len(piece)
        inserts.setdefault(k, []).append(f"（{piece}）")
    if not inserts:
        return None
    out: list[str] = []
    for k, ch_idx in enumerate(kmap):
        if k == 0:
            out.append(chunk[:ch_idx])
        out.append(chunk[ch_idx])
        if k in inserts:
            out.extend(inserts[k])
        nxt = kmap[k + 1] if k + 1 < len(kmap) else len(chunk)
        out.append(chunk[ch_idx + 1 : nxt])  # 段内原有的换行照留
    return "".join(out)


async def chunks_with_notes(db: AsyncSession, chunks: list[dict]) -> dict[int, str]:
    """chunks：[{text_id, juan_num, chunk_text, lang}]。返回 {下标: 插好夹注的段落}，只含真的附上了夹注的。"""
    want = {(c["text_id"], c["juan_num"]) for c in chunks if c.get("lang", "lzh") == "lzh" and c.get("chunk_text")}
    if not want:
        return {}
    tids = {t for t, _ in want}
    rows = (
        await db.execute(
            select(TextInlineNote.text_id, TextInlineNote.juan_num, TextInlineNote.char_offset, TextInlineNote.content)
            .where(TextInlineNote.text_id.in_(tids))
            .order_by(TextInlineNote.text_id, TextInlineNote.juan_num, TextInlineNote.seq)
        )
    ).all()
    notes: dict[tuple[int, int], list[tuple[int, str]]] = {}
    for t, j, off, text in rows:
        if (t, j) in want:
            notes.setdefault((t, j), []).append((off, text))
    if not notes:
        return {}
    contents = {
        (t, j): c
        for t, j, c in (
            await db.execute(
                select(TextContent.text_id, TextContent.juan_num, TextContent.content).where(
                    TextContent.text_id.in_({t for t, _ in notes}), TextContent.lang == "lzh"
                )
            )
        ).all()
        if (t, j) in notes
    }
    out: dict[int, str] = {}
    for i, c in enumerate(chunks):
        key = (c.get("text_id"), c.get("juan_num"))
        if key in notes and key in contents:
            spliced = splice_notes(c["chunk_text"], contents[key], notes[key])
            if spliced:
                out[i] = spliced
    return out
