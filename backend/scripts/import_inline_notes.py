"""Import CBETA 夹注 / 双行小注 (<note place="inline">) into text_inline_notes.

The body text in text_contents never contained these notes (the parser skipped every <note>),
and must not start to: line anchors, apparatus offsets, ?hl= quote highlights, search and
embeddings all index into it. So the notes go into their own table, positioned by offset, and
the reader splices them back in.

Safety: offsets come from the freshly parsed XML body. When it equals the stored body character
for character, they are used as is. When it differs (stored body from an older parser — 「┌│」 vs
全角空格 — or a juan fixed by hand), each note is placed by the 8 characters before it (else after
it), ignoring line breaks, and only if that context occurs exactly once in the stored juan; a juan
where fewer than half the notes can be placed is skipped whole. The stored body is never changed.

Idempotent per work (delete + reinsert). Only touches text_inline_notes.

Usage (run in a one-off container, not the live backend — see memory: imports OOM the 1GB limit):
    python scripts/import_inline_notes.py --work T2154
    python scripts/import_inline_notes.py --all [--xml-dir /xml]
"""

import argparse
import asyncio
import logging
import os
import sys

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.core.xml_parser import find_all_xml_files, parse_tei_xml
from app.models.text import BuddhistText, TextContent, TextInlineNote

logger = logging.getLogger("import_inline_notes")
DEFAULT_XML_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "xml-p5")


def _has_inline_notes(path) -> bool:
    with open(path, encoding="utf8") as f:
        return 'place="inline"' in f.read()


UNIQUE_CONTEXT = 8  # 逐条找时用夹注前（或后）这么多字，在库里正文中必须恰好出现一次


def locate_by_context(parsed: str, stored: str, notes: list[dict]) -> tuple[list[dict], int]:
    """段落次序被手工调过的卷（資持記卷11）：整卷对齐失效，逐条用夹注前 8 字（不行再用后 8 字）
    在库里正文里找，恰好出现一次才放，否则丢掉这一条。比较时不计换行（两版硬换行位置不同）。"""
    keep = [i for i, ch in enumerate(stored) if ch != "\n"]  # 去换行后的第 k 字 → 原下标
    flat = "".join(stored[i] for i in keep)
    out: list[dict] = []
    dropped = 0
    for n in notes:
        o = n["offset"]
        before = parsed[:o].replace("\n", "")[-UNIQUE_CONTEXT:]
        after = parsed[o:].replace("\n", "")[:UNIQUE_CONTEXT]
        m = None
        if len(before) == UNIQUE_CONTEXT and flat.count(before) == 1:
            m = keep[flat.index(before) + UNIQUE_CONTEXT - 1] + 1
        elif len(after) == UNIQUE_CONTEXT and flat.count(after) == 1:
            m = keep[flat.index(after)]
        if m is None:
            dropped += 1
        else:
            out.append({**n, "offset": m})
    return out, dropped


def notes_for_work(xml_files, stored: dict[int, str]) -> tuple[dict[int, list[dict]], list[int], int, int]:
    """{juan_num: [notes]}；跳过的卷（两份正文差太多）；搬过位置的卷数；搬时丢掉的条数。"""
    # 一部经分几个文件时卷号会重复（資持記：库里卷11 是另一个文件的卷11）——同号的卷都留着，挑和库里对得上的那个
    parsed: dict[int, list[dict]] = {}
    for xml_file in xml_files:
        for j in parse_tei_xml(xml_file):
            parsed.setdefault(j["juan_num"], []).append(j)
    ok: dict[int, list[dict]] = {}
    skipped: list[int] = []
    remapped = dropped = 0
    for jn, cands in parsed.items():
        cands = [j for j in cands if j.get("inline_notes")]
        if not cands or jn not in stored:
            continue
        exact = next((j for j in cands if j["content"] == stored[jn]), None)
        if exact:
            ok[jn] = exact["inline_notes"]
            continue
        best = None
        for j in cands:
            r = locate_by_context(j["content"], stored[jn], j["inline_notes"])
            # 一半都找不到：不是同一段文字（資持記卷11 是另一种编排），这一卷不写
            if len(r[0]) >= 0.5 * len(j["inline_notes"]) and (best is None or len(r[0]) > len(best[0])):
                best = r
        if best is None:
            skipped.append(jn)
            continue
        ok[jn], d = best
        remapped += 1
        dropped += d
    return ok, sorted(skipped), remapped, dropped


async def import_work(session: AsyncSession, bt: BuddhistText, xml_dir: str) -> dict:
    xml_files = [f for f in find_all_xml_files(bt.cbeta_id, xml_dir) if _has_inline_notes(f)]
    if not xml_files:
        return {}
    res = await session.execute(
        select(TextContent.juan_num, TextContent.content).where(TextContent.text_id == bt.id, TextContent.lang == "lzh")
    )
    stored = {jn: c for jn, c in res.all()}
    if not stored:
        return {}
    ok, skipped, remapped, dropped = notes_for_work(xml_files, stored)
    if skipped:
        logger.warning("%s: juans %s differ too much from stored content — notes not written", bt.cbeta_id, skipped[:10])
    if remapped:
        logger.warning("%s: %d juans remapped onto stored content, %d notes dropped", bt.cbeta_id, remapped, dropped)
    await session.execute(delete(TextInlineNote).where(TextInlineNote.text_id == bt.id))
    n = chars = 0
    for jn, notes in ok.items():
        for seq, note in enumerate(notes):
            session.add(TextInlineNote(text_id=bt.id, juan_num=jn, char_offset=note["offset"], seq=seq,
                                       content=note["text"]))  # fmt: skip
            n += 1
            chars += len(note["text"])
    await session.commit()
    session.expunge_all()
    return {"notes": n, "chars": chars, "juans": len(ok), "juans_skipped": len(skipped), "juans_remapped": remapped,
            "notes_dropped": dropped}  # fmt: skip


async def main() -> None:
    parser = argparse.ArgumentParser(description="Import CBETA inline notes (夹注)")
    parser.add_argument("--work", type=str, help="Single work ID (e.g. T2154)")
    parser.add_argument("--all", action="store_true", help="Every CBETA work")
    parser.add_argument("--works-file", type=str, help="File with one cbeta_id per line (re-run just these)")
    parser.add_argument("--xml-dir", type=str, default=DEFAULT_XML_DIR)
    args = parser.parse_args()
    if not args.work and not args.all and not args.works_file:
        parser.error("--work, --works-file or --all is required")

    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            q = select(BuddhistText).where(BuddhistText.lang == "lzh").order_by(BuddhistText.cbeta_id)
            if args.work:
                q = q.where(BuddhistText.cbeta_id == args.work)
            elif args.works_file:
                with open(args.works_file, encoding="utf8") as f:
                    q = q.where(BuddhistText.cbeta_id.in_([w.strip() for w in f if w.strip()]))
            texts = (await session.execute(q)).scalars().all()
            tot = {"works": 0, "notes": 0, "chars": 0, "juans": 0, "juans_skipped": 0, "juans_remapped": 0,
                   "notes_dropped": 0}  # fmt: skip
            for i, bt in enumerate(texts):
                c = await import_work(session, bt, args.xml_dir)
                if c.get("notes"):
                    tot["works"] += 1
                for k in ("notes", "chars", "juans", "juans_skipped", "juans_remapped", "notes_dropped"):
                    tot[k] += c.get(k, 0)
                if args.work:
                    print(f"{bt.cbeta_id}: {c}")
                elif (i + 1) % 200 == 0:
                    print(f"  {i + 1}/{len(texts)} {tot}", flush=True)
            print(f"Done. {tot}", flush=True)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
