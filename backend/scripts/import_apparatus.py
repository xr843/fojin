"""Import CBETA critical apparatus (校勘异文) + <lb> line anchors into PostgreSQL.

Reads the same CBETA xml-p5 repo as import_content.py, parses the standoff
<app> apparatus and resolves each variant to a (juan, char_start, char_end)
offset against the body content that import_content stored, then writes
text_apparatus / apparatus_reading / text_line_anchors.

Idempotent per work: existing rows for a text are deleted before reinsert, so
re-running (or --resume) is safe. Run AFTER import_content has populated
text_contents — offsets are validated against the stored body.

Usage:
    python scripts/import_apparatus.py --work T0001
    python scripts/import_apparatus.py --collection T --xml-dir data/xml-p5
    python scripts/import_apparatus.py --all --resume
"""

import argparse
import asyncio
import json
import logging
import os
import sys

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.core.xml_parser import find_all_xml_files, parse_tei_apparatus
from app.models.text import (
    ApparatusReading,
    BuddhistText,
    TextApparatus,
    TextContent,
    TextLineAnchor,
)

logger = logging.getLogger("import_apparatus")

# CBETA canon collections that carry a standoff apparatus. Non-CBETA sources
# (SuttaCentral SC-, GRETIL) have no <app> and simply yield nothing.
ALL_COLLECTIONS = ["T", "X", "A", "K", "S", "F", "C", "D", "U", "P", "J", "L", "G", "M", "N", "B",
                   "GA", "GB", "ZS", "I", "ZW", "Y", "TX", "LC"]

DEFAULT_XML_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "xml-p5")
CHECKPOINT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "checkpoints", "import_apparatus.json",
)


def load_checkpoint() -> dict:
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {}


def save_checkpoint(data: dict):
    os.makedirs(os.path.dirname(CHECKPOINT_FILE), exist_ok=True)
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clear_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)


async def import_work(session: AsyncSession, bt: BuddhistText, xml_dir: str) -> dict:
    """Parse + store apparatus and line anchors for one work, then commit.

    Alignment is validated against the body content ALREADY STORED in
    text_contents (not the freshly parsed XML), so XML/DB drift can only
    downgrade an entry to aligned=False — never silently misposition it.

    Returns counts: {entries, aligned, skipped_no_juan, readings, line_anchors}.
    """
    xml_files = find_all_xml_files(bt.cbeta_id, xml_dir)
    if not xml_files:
        return {}

    # Stored body content this work's offsets must match.
    res = await session.execute(
        select(TextContent.juan_num, TextContent.content).where(TextContent.text_id == bt.id)
    )
    stored_content = {jn: c for jn, c in res.all()}
    if not stored_content:
        logger.warning("%s: no stored content — run import_content first; skipping", bt.cbeta_id)
        return {}

    # Collect apparatus entries + line anchors across all files of the work.
    entries: list[dict] = []
    line_rows: list[dict] = []
    seen_app: set[tuple] = set()
    seen_line: set[tuple] = set()
    drift = 0
    for xml_file in xml_files:
        data = parse_tei_apparatus(xml_file)
        for e in data["entries"]:
            if e["juan_num"] is None:
                entries.append(e)  # unlocatable (preface/skipped tag) — counted, not stored
                continue
            key = (e["juan_num"], e["app_n"])
            if key in seen_app:
                continue
            seen_app.add(key)
            # Re-validate against the stored body, not the parsed XML.
            if e["aligned"] and e["char_start"] is not None:
                span = stored_content.get(e["juan_num"], "")[e["char_start"]:e["char_end"]]
                if span.replace("\n", "").replace(" ", "") != e["lemma"]:
                    e = {**e, "aligned": False}
                    drift += 1
            entries.append(e)
        for la in data["line_anchors"]:
            key = (la["juan_num"], la["line"])
            if key in seen_line:
                continue
            seen_line.add(key)
            line_rows.append(la)

    if drift:
        logger.warning("%s: %d entries failed stored-content re-validation (XML/DB drift)", bt.cbeta_id, drift)

    # Idempotent reinsert.
    await session.execute(delete(TextApparatus).where(TextApparatus.text_id == bt.id))
    await session.execute(delete(TextLineAnchor).where(TextLineAnchor.text_id == bt.id))

    aligned = skipped = readings = 0
    for e in entries:
        if e["juan_num"] is None:
            skipped += 1
            continue
        if e["aligned"]:
            aligned += 1
        readings += len(e["readings"])
        session.add(TextApparatus(
            text_id=bt.id,
            juan_num=e["juan_num"],
            char_start=e["char_start"],
            char_end=e["char_end"],
            lemma=e["lemma"],
            lemma_siglum=e["lemma_siglum"],
            app_n=e["app_n"],
            aligned=e["aligned"],
            readings=[
                ApparatusReading(
                    reading=r["reading"],
                    witnesses=r["witnesses"],
                    resp=r["resp"] or None,
                    is_omission=r["is_omission"],
                )
                for r in e["readings"]
            ],
        ))
    for la in line_rows:
        session.add(TextLineAnchor(
            text_id=bt.id,
            juan_num=la["juan_num"],
            char_offset=la["offset"],
            line_ref=la["line"],
        ))

    # Commit + clear the identity map per work so memory stays bounded across a
    # large collection (T01n0001 alone is ~3k entries + ~11k line anchors).
    await session.commit()
    session.expunge_all()

    stored = sum(1 for e in entries if e["juan_num"] is not None)
    return {
        "entries": stored,
        "aligned": aligned,
        "skipped_no_juan": skipped,
        "readings": readings,
        "line_anchors": len(line_rows),
    }


async def get_texts_for_collection(session: AsyncSession, collection: str) -> list[BuddhistText]:
    result = await session.execute(
        select(BuddhistText).where(BuddhistText.cbeta_id.startswith(collection)).order_by(BuddhistText.cbeta_id)
    )
    return list(result.scalars().all())


async def import_collection(session_factory, collection, xml_dir, limit=0, resume_after=None) -> tuple:
    """Returns (works_with_apparatus, total_entries, total_aligned, last_cbeta_id)."""
    async with session_factory() as session:
        texts = await get_texts_for_collection(session, collection)
        if limit > 0:
            texts = texts[:limit]
        if resume_after:
            skip = True
            filtered = []
            for bt in texts:
                if skip:
                    if bt.cbeta_id == resume_after:
                        skip = False
                    continue
                filtered.append(bt)
            texts = filtered
            print(f"  Resuming after {resume_after}, {len(texts)} remaining.")
        if not texts:
            return 0, 0, 0, None

        works = total_entries = total_aligned = 0
        last_id = None
        for i, bt in enumerate(texts):
            counts = await import_work(session, bt, xml_dir)
            if counts.get("entries"):
                works += 1
                total_entries += counts["entries"]
                total_aligned += counts["aligned"]
            last_id = bt.cbeta_id
            if (i + 1) % 50 == 0:
                await session.commit()
                pct = (100 * total_aligned / total_entries) if total_entries else 0
                print(f"  [{collection}] {i + 1}/{len(texts)} works, {works} w/ apparatus, "
                      f"{total_entries} entries ({pct:.1f}% aligned)")
                save_checkpoint({"collection": collection, "last_cbeta_id": last_id,
                                 "works": works, "total_entries": total_entries})
        await session.commit()
        return works, total_entries, total_aligned, last_id


async def main():
    parser = argparse.ArgumentParser(description="Import CBETA critical apparatus")
    parser.add_argument("--collection", type=str, help="Collection prefix (e.g. T, X)")
    parser.add_argument("--work", type=str, help="Single work ID (e.g. T0001)")
    parser.add_argument("--xml-dir", type=str, default=DEFAULT_XML_DIR)
    parser.add_argument("--limit", type=int, default=0, help="Limit works (0=all)")
    parser.add_argument("--all", action="store_true", help="All CBETA collections")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    args = parser.parse_args()

    if not args.collection and not args.work and not args.all:
        parser.error("Either --collection, --work, or --all is required")

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        if args.work:
            async with session_factory() as session:
                result = await session.execute(
                    select(BuddhistText).where(BuddhistText.cbeta_id == args.work)
                )
                bt = result.scalar_one_or_none()
                if not bt:
                    print(f"Work {args.work} not found")
                    return
                counts = await import_work(session, bt, args.xml_dir)
                await session.commit()
                print(f"{args.work}: {counts}")
        else:
            collections = ALL_COLLECTIONS if args.all else [args.collection]
            checkpoint = load_checkpoint() if args.resume else {}
            resume_collection = checkpoint.get("collection")
            resume_after = checkpoint.get("last_cbeta_id")
            grand_entries = grand_aligned = 0
            started = resume_collection is None
            for col in collections:
                if not started:
                    if col == resume_collection:
                        started = True
                    else:
                        continue
                after = resume_after if col == resume_collection else None
                works, entries, aligned, _ = await import_collection(
                    session_factory, col, args.xml_dir, limit=args.limit, resume_after=after
                )
                grand_entries += entries
                grand_aligned += aligned
                if entries:
                    print(f"[{col}] {works} works, {entries} entries, {aligned} aligned")
            clear_checkpoint()
            pct = (100 * grand_aligned / grand_entries) if grand_entries else 0
            print(f"\nDone. {grand_entries} apparatus entries, {grand_aligned} aligned ({pct:.1f}%).")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
