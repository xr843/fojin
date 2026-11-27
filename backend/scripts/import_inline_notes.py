"""Import CBETA 夹注 / 双行小注 (<note place="inline">) into text_inline_notes.

The body text in text_contents never contained these notes (the parser skipped every <note>),
and must not start to: line anchors, apparatus offsets, ?hl= quote highlights, search and
embeddings all index into it. So the notes go into their own table, positioned by offset, and
the reader splices them back in.

Safety: a juan's notes are only written when the freshly parsed body equals the stored body
character for character (same rule as line anchors in import_apparatus) — otherwise the offsets
could point at the wrong characters (XML from another CBETA release, a juan fixed by hand).
Such juans are skipped and counted.

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


def notes_for_work(xml_files, stored: dict[int, str]) -> tuple[dict[int, list[dict]], list[int]]:
    """{juan_num: [notes]} for juans whose parsed body equals the stored body; plus the juans
    skipped because they differ. A juan split over several files keeps the first file's parse
    (same as import_apparatus)."""
    parsed: dict[int, dict] = {}
    for xml_file in xml_files:
        for j in parse_tei_xml(xml_file):
            parsed.setdefault(j["juan_num"], j)
    ok: dict[int, list[dict]] = {}
    skipped: list[int] = []
    for jn, j in parsed.items():
        if not j.get("inline_notes"):
            continue
        if stored.get(jn) == j["content"]:
            ok[jn] = j["inline_notes"]
        else:
            skipped.append(jn)
    return ok, sorted(skipped)


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
    ok, skipped = notes_for_work(xml_files, stored)
    if skipped:
        logger.warning("%s: juans %s differ from stored content — notes not written", bt.cbeta_id, skipped[:10])
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
    return {"notes": n, "chars": chars, "juans": len(ok), "juans_skipped": len(skipped)}


async def main() -> None:
    parser = argparse.ArgumentParser(description="Import CBETA inline notes (夹注)")
    parser.add_argument("--work", type=str, help="Single work ID (e.g. T2154)")
    parser.add_argument("--all", action="store_true", help="Every CBETA work")
    parser.add_argument("--xml-dir", type=str, default=DEFAULT_XML_DIR)
    args = parser.parse_args()
    if not args.work and not args.all:
        parser.error("--work or --all is required")

    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            q = select(BuddhistText).where(BuddhistText.lang == "lzh").order_by(BuddhistText.cbeta_id)
            if args.work:
                q = q.where(BuddhistText.cbeta_id == args.work)
            texts = (await session.execute(q)).scalars().all()
            tot = {"works": 0, "notes": 0, "chars": 0, "juans": 0, "juans_skipped": 0}
            for i, bt in enumerate(texts):
                c = await import_work(session, bt, args.xml_dir)
                if c.get("notes"):
                    tot["works"] += 1
                for k in ("notes", "chars", "juans", "juans_skipped"):
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
