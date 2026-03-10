"""
Import CBETA text content from XML files into PostgreSQL and Elasticsearch.

Usage:
    python scripts/import_content.py --collection T
    python scripts/import_content.py --collection T --xml-dir /path/to/xml-p5
    python scripts/import_content.py --work T0251
    python scripts/import_content.py --all --xml-dir data/xml-p5
    python scripts/import_content.py --all --resume

The script expects CBETA xml-p5 repository to be cloned locally.
If not found, it will attempt to clone it (shallow clone).
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import select, text, update

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.elasticsearch import CONTENT_INDEX_NAME
from app.core.xml_parser import find_all_xml_files, parse_tei_xml
from app.models.text import BuddhistText

DEFAULT_XML_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "xml-p5")
CBETA_XML_REPO = "https://github.com/cbeta-org/xml-p5.git"

# All CBETA collection prefixes
ALL_COLLECTIONS = ["T", "X", "A", "K", "S", "F", "C", "D", "U", "P", "J", "L", "G", "M", "N", "B", "GA", "GB",
                   "ZS", "I", "ZW", "Y", "TX", "LC"]

CHECKPOINT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "checkpoints", "import_content.json",
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
        os.unlink(CHECKPOINT_FILE)


def ensure_xml_repo(xml_dir: str, collection: str | None = None):
    """Ensure the CBETA XML repository is available locally."""
    if os.path.exists(xml_dir) and os.listdir(xml_dir):
        print(f"  XML directory exists: {xml_dir}")
        # If we need a specific collection, sparse checkout it
        if collection and not os.path.exists(os.path.join(xml_dir, collection)):
            git_dir = xml_dir
            try:
                subprocess.run(
                    ["git", "-C", git_dir, "sparse-checkout", "add", collection],
                    check=True, capture_output=True,
                )
                print(f"  Sparse checkout added for collection '{collection}'.")
            except Exception as e:
                print(f"  Warning: could not sparse checkout '{collection}': {e}")
        return

    print(f"  Cloning CBETA xml-p5 repository to {xml_dir}...")
    os.makedirs(xml_dir, exist_ok=True)

    cmd = ["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", CBETA_XML_REPO, xml_dir]
    subprocess.run(cmd, check=True)

    if collection:
        # Sparse checkout only the needed collection
        subprocess.run(["git", "-C", xml_dir, "sparse-checkout", "set", collection], check=True)
        print(f"  Sparse checkout for collection '{collection}' done.")


async def get_texts_for_collection(session: AsyncSession, collection: str) -> list[BuddhistText]:
    """Get all BuddhistText records for a given collection prefix."""
    result = await session.execute(
        select(BuddhistText).where(BuddhistText.cbeta_id.startswith(collection))
    )
    return list(result.scalars().all())


async def get_single_text(session: AsyncSession, work_id: str) -> BuddhistText | None:
    """Get a single BuddhistText by cbeta_id."""
    result = await session.execute(
        select(BuddhistText).where(BuddhistText.cbeta_id == work_id)
    )
    return result.scalar_one_or_none()


async def import_work(
    session: AsyncSession,
    es: AsyncElasticsearch,
    bt: BuddhistText,
    xml_dir: str,
) -> int:
    """Import content for a single work. Returns number of juans imported."""
    xml_files = find_all_xml_files(bt.cbeta_id, xml_dir)
    if not xml_files:
        return 0

    all_juans = []
    for xml_file in xml_files:
        juans = parse_tei_xml(xml_file)
        all_juans.extend(juans)

    if not all_juans:
        return 0

    # Deduplicate by juan_num (keep first occurrence)
    seen_juans = set()
    unique_juans = []
    for j in all_juans:
        if j["juan_num"] not in seen_juans:
            seen_juans.add(j["juan_num"])
            unique_juans.append(j)

    # Insert into text_contents
    total_chars = 0
    for j in unique_juans:
        await session.execute(
            text("""
                INSERT INTO text_contents (text_id, juan_num, content, char_count, lang)
                VALUES (:text_id, :juan_num, :content, :char_count, 'lzh')
                ON CONFLICT ON CONSTRAINT uq_text_content_text_juan_lang DO UPDATE SET
                    content = EXCLUDED.content,
                    char_count = EXCLUDED.char_count
            """),
            {
                "text_id": bt.id,
                "juan_num": j["juan_num"],
                "content": j["content"],
                "char_count": j["char_count"],
            },
        )
        total_chars += j["char_count"]

    # Update buddhist_texts
    await session.execute(
        update(BuddhistText)
        .where(BuddhistText.id == bt.id)
        .values(has_content=True, content_char_count=total_chars)
    )

    # Index content into Elasticsearch
    async def gen_es_actions():
        for j in unique_juans:
            yield {
                "_index": CONTENT_INDEX_NAME,
                "_id": f"{bt.id}_{j['juan_num']}_lzh",
                "_source": {
                    "text_id": bt.id,
                    "cbeta_id": bt.cbeta_id,
                    "title_zh": bt.title_zh,
                    "translator": bt.translator,
                    "dynasty": bt.dynasty,
                    "juan_num": j["juan_num"],
                    "content": j["content"],
                    "char_count": j["char_count"],
                    "lang": "lzh",
                    "source_code": "cbeta",
                },
            }

    await async_bulk(es, gen_es_actions(), raise_on_error=False)

    return len(unique_juans)


async def import_collection(
    session_factory,
    es: AsyncElasticsearch,
    collection: str,
    xml_dir: str,
    limit: int = 0,
    resume_after: str | None = None,
) -> tuple[int, int, str | None]:
    """Import all works in a collection. Returns (imported_count, juan_count, last_cbeta_id)."""
    async with session_factory() as session:
        texts = await get_texts_for_collection(session, collection)

        if limit > 0:
            texts = texts[:limit]

        # Resume: skip already processed
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
            return 0, 0, None

        imported = 0
        total_juans = 0
        last_id = None

        for i, bt in enumerate(texts):
            n_juans = await import_work(session, es, bt, xml_dir)
            if n_juans > 0:
                imported += 1
                total_juans += n_juans

            last_id = bt.cbeta_id

            if (i + 1) % 50 == 0:
                await session.commit()
                print(f"  [{collection}] Progress: {i + 1}/{len(texts)} works, "
                      f"{imported} with content, {total_juans} juans")
                # Save checkpoint
                save_checkpoint({
                    "collection": collection,
                    "last_cbeta_id": last_id,
                    "imported": imported,
                    "total_juans": total_juans,
                })

        await session.commit()
        return imported, total_juans, last_id


async def main():
    parser = argparse.ArgumentParser(description="Import CBETA text content")
    parser.add_argument("--collection", type=str, help="Collection prefix (e.g. T, X)")
    parser.add_argument("--work", type=str, help="Single work ID (e.g. T0251)")
    parser.add_argument("--xml-dir", type=str, default=DEFAULT_XML_DIR, help="Path to xml-p5 directory")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of works to import (0=all)")
    parser.add_argument("--all", action="store_true", help="Import all collections")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    args = parser.parse_args()

    if not args.collection and not args.work and not args.all:
        parser.error("Either --collection, --work, or --all is required")

    print("=" * 60)
    print("佛津 (FoJin) — CBETA Content Import")
    print("=" * 60)

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    es = AsyncElasticsearch(settings.es_host)

    try:
        if args.work:
            # Single work mode
            print("\n[1/2] Ensuring XML repository...")
            collection = args.work[0] if args.work else None
            ensure_xml_repo(args.xml_dir, collection)

            async with session_factory() as session:
                print("\n[2/2] Importing single work...")
                bt = await get_single_text(session, args.work)
                if bt is None:
                    print(f"  Work '{args.work}' not found in database. Run import_catalog.py first.")
                    return
                n_juans = await import_work(session, es, bt, args.xml_dir)
                await session.commit()
                print(f"  Imported {n_juans} juans for {args.work}")

        elif args.all:
            # All collections mode
            checkpoint = load_checkpoint() if args.resume else {}
            resume_collection = checkpoint.get("collection")
            resume_after = checkpoint.get("last_cbeta_id")

            total_imported = 0
            total_juans = 0
            skip_collections = True if resume_collection else False

            for col in ALL_COLLECTIONS:
                if skip_collections:
                    if col == resume_collection:
                        skip_collections = False
                        # Resume within this collection
                    else:
                        continue

                print(f"\n{'─' * 40}")
                print(f"  Collection: {col}")
                print(f"{'─' * 40}")

                ensure_xml_repo(args.xml_dir, col)

                col_resume = resume_after if col == resume_collection else None
                imported, juans, last_id = await import_collection(
                    session_factory, es, col, args.xml_dir,
                    limit=args.limit, resume_after=col_resume,
                )
                total_imported += imported
                total_juans += juans
                print(f"  [{col}] Done: {imported} works, {juans} juans")

                resume_after = None  # Only resume for first collection

            clear_checkpoint()
            print(f"\nAll collections imported: {total_imported} works, {total_juans} juans")

        else:
            # Single collection mode
            print("\n[1/3] Ensuring XML repository...")
            ensure_xml_repo(args.xml_dir, args.collection)

            checkpoint = load_checkpoint() if args.resume else {}
            resume_after = checkpoint.get("last_cbeta_id") if args.resume else None

            print(f"\n[2/3] Importing collection {args.collection}...")
            imported, juans, _ = await import_collection(
                session_factory, es, args.collection, args.xml_dir,
                limit=args.limit, resume_after=resume_after,
            )

            clear_checkpoint()
            print(f"\n[3/3] Import complete!")
            print(f"  Works with content: {imported}")
            print(f"  Total juans imported: {juans}")

        print("=" * 60)

    finally:
        await es.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
