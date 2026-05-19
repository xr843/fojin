"""
Import Kanripo (漢籍リポジトリ) Taisho catalog from their GitHub org-mode file.

Source: https://github.com/kanripo/KR-Catalog/blob/master/taisho.org
Contains 3,017 entries from the Taishō Shinshū Daizōkyō (大正新脩大藏經).

For texts already in our DB (matched by normalized T-number),
we add a TextIdentifier linking to Kanripo.
For new texts, we create a BuddhistText record + ES index entry.
"""

import asyncio
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.base_importer import BaseImporter


def parse_kanripo_catalog(filepath: str) -> list[dict]:
    """Parse the Kanripo taisho.org file in org-mode format.

    Each entry looks like:
        *** T08n0251 般若波羅蜜多心經
        :PROPERTIES:
        :KR_ID: KR6c0128
        :CUSTOM_ID: T08n0251
        :lang@ja-rom: HANNYAHARAMITTA SHIN GYŌ
        :lang@zh-py: (Pan ruo bo luo mi duo xin jing)
        :lang@sk: *P°p°hṛdaya
        :EXTENT: I
        :END:
        **** 人物
        ***** 玄奘
    """
    entries = []
    current_entry = None
    current_section = None  # "main" or "category"
    current_category = ""
    in_properties = False
    current_person = None

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")

            # Category header: ** I 阿含 A han, Part 1.
            if line.startswith("** ") and not line.startswith("*** "):
                # Extract Chinese category name
                m = re.search(r'[\u4e00-\u9fff]+', line[3:])
                if m:
                    current_category = m.group(0)
                continue

            # Entry header: *** T01n0001 長阿含經
            m = re.match(r'^\*\*\* (T\d+n\d+)\s+(.+)', line)
            if m:
                if current_entry:
                    entries.append(current_entry)
                current_entry = {
                    "kanripo_id": m.group(1),
                    "title_zh": m.group(2).strip(),
                    "category": current_category,
                    "kr_id": None,
                    "pinyin": None,
                    "sanskrit": None,
                    "japanese_rom": None,
                    "extent": None,
                    "translators": [],
                }
                in_properties = False
                current_person = None
                current_section = "main"
                continue

            if not current_entry:
                continue

            # Sub-section header: **** 人物
            if line.startswith("**** "):
                current_section = line[5:].strip()
                continue

            # Person name: ***** 玄奘
            if line.startswith("***** "):
                name = line[6:].strip()
                if current_section == "人物" and name:
                    current_entry["translators"].append(name)
                    current_person = name
                continue

            # Properties block
            if line.strip() == ":PROPERTIES:":
                in_properties = True
                continue
            if line.strip() == ":END:":
                in_properties = False
                continue

            if in_properties and current_entry and current_section == "main":
                # :KR_ID: KR6a0001
                pm = re.match(r'^:(\S+):\s*(.*)', line.strip())
                if pm:
                    key, val = pm.group(1), pm.group(2).strip()
                    if key == "KR_ID":
                        current_entry["kr_id"] = val
                    elif key == "CUSTOM_ID":
                        pass  # same as kanripo_id
                    elif key == "lang@zh-py":
                        current_entry["pinyin"] = val.strip("()")
                    elif key == "lang@sk":
                        current_entry["sanskrit"] = val.lstrip("*")
                    elif key == "lang@ja-rom":
                        current_entry["japanese_rom"] = val
                    elif key == "EXTENT":
                        current_entry["extent"] = val

    # Don't forget the last entry
    if current_entry:
        entries.append(current_entry)

    return entries


def normalize_cbeta_id(kanripo_id: str) -> str:
    """Convert Kanripo ID (T08n0251) to CBETA-style ID (T0251).

    Kanripo format: T{volume}n{number}
    CBETA format: T{number}
    """
    m = re.match(r'^T\d+n(\d+[a-zA-Z]?)$', kanripo_id)
    if m:
        num = m.group(1)
        # Remove leading zeros but keep at least 4 digits for consistency
        return f"T{num}"
    return kanripo_id


def parse_extent_to_count(extent: str | None) -> int | None:
    """Convert Roman numeral extent to fascicle count."""
    if not extent:
        return None
    roman_map = {
        "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
        "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
        "XI": 11, "XII": 12, "XIII": 13, "XIV": 14, "XV": 15,
        "XVI": 16, "XVII": 17, "XVIII": 18, "XIX": 19, "XX": 20,
        "XXI": 21, "XXII": 22, "XXIII": 23, "XXIV": 24, "XXV": 25,
        "XXVI": 26, "XXVII": 27, "XXVIII": 28, "XXIX": 29, "XXX": 30,
        "XL": 40, "L": 50, "LX": 60, "LXX": 70, "LXXX": 80, "XC": 90, "C": 100,
    }
    extent = extent.strip()
    if extent in roman_map:
        return roman_map[extent]
    # Try parsing as integer
    try:
        return int(extent)
    except ValueError:
        return None


class KanripoCatalogImporter(BaseImporter):
    SOURCE_CODE = "kanseki-repo"
    SOURCE_NAME_ZH = "漢籍リポジトリ(Kanseki)"
    SOURCE_NAME_EN = "Kanseki Repository (Kanripo)"
    SOURCE_BASE_URL = "https://www.kanripo.org"
    SOURCE_DESCRIPTION = "Kanripo Taisho catalog — 3,017 entries from 大正新脩大藏經"

    def __init__(self, catalog_path: str = "/tmp/taisho.org"):
        super().__init__()
        self.catalog_path = catalog_path

    async def run_import(self):
        # 1. Parse catalog
        print(f"\n[1/3] Parsing catalog: {self.catalog_path}")
        entries = parse_kanripo_catalog(self.catalog_path)
        print(f"  Parsed {len(entries)} entries")

        # 2. Load existing CBETA IDs for dedup
        print(f"\n[2/3] Loading existing texts for dedup...")
        async with self.session_factory() as session:
            source = await self.ensure_source(session)
            source_id = source.id
            await session.commit()

            # Get all existing cbeta_ids and their DB ids
            result = await session.execute(
                sa_text("SELECT id, cbeta_id FROM buddhist_texts")
            )
            existing = {}
            for row in result.fetchall():
                existing[row[1]] = row[0]
            print(f"  Existing texts: {len(existing)}")

            # Get existing identifiers to avoid duplicates
            result = await session.execute(
                sa_text("SELECT text_id, source_uid FROM text_identifiers WHERE source_id = :sid"),
                {"sid": source_id},
            )
            existing_idents = set()
            for row in result.fetchall():
                existing_idents.add(row[1])
            print(f"  Existing Kanripo identifiers: {len(existing_idents)}")

        # 3. Import
        print(f"\n[3/3] Importing...")
        batch_size = 100
        new_texts = []
        identifier_links = []
        es_docs = []

        for entry in entries:
            cbeta_id = normalize_cbeta_id(entry["kanripo_id"])
            translator = ", ".join(entry["translators"]) if entry["translators"] else None
            fascicle_count = parse_extent_to_count(entry["extent"])

            if cbeta_id in existing:
                # Text already exists — just add identifier if not present
                if entry["kanripo_id"] not in existing_idents:
                    identifier_links.append({
                        "text_id": existing[cbeta_id],
                        "kanripo_id": entry["kanripo_id"],
                        "kr_id": entry["kr_id"],
                    })
                    self.stats.identifiers_created += 1
                else:
                    self.stats.skipped += 1
            else:
                # New text
                new_texts.append({
                    "cbeta_id": cbeta_id,
                    "kanripo_id": entry["kanripo_id"],
                    "title_zh": entry["title_zh"],
                    "title_sa": entry["sanskrit"],
                    "translator": translator,
                    "category": entry["category"],
                    "fascicle_count": fascicle_count,
                    "source_id": source_id,
                    "lang": "lzh",
                    "kr_id": entry["kr_id"],
                })

        print(f"  New texts to create: {len(new_texts)}")
        print(f"  Identifiers to link: {len(identifier_links)}")
        print(f"  Skipped (already linked): {self.stats.skipped}")

        # Insert new texts in batches
        async with self.session_factory() as session:
            for i in range(0, len(new_texts), batch_size):
                batch = new_texts[i:i + batch_size]
                for t in batch:
                    result = await session.execute(
                        sa_text("""
                            INSERT INTO buddhist_texts
                                (cbeta_id, title_zh, title_sa, translator, category,
                                 fascicle_count, source_id, lang, has_content, content_char_count)
                            VALUES
                                (:cbeta_id, :title_zh, :title_sa, :translator, :category,
                                 :fascicle_count, :source_id, :lang, false, 0)
                            ON CONFLICT (cbeta_id) DO NOTHING
                            RETURNING id
                        """),
                        {
                            "cbeta_id": t["cbeta_id"],
                            "title_zh": t["title_zh"],
                            "title_sa": t["title_sa"],
                            "translator": t["translator"],
                            "category": t["category"],
                            "fascicle_count": t["fascicle_count"],
                            "source_id": t["source_id"],
                            "lang": t["lang"],
                        },
                    )
                    row = result.fetchone()
                    if row:
                        text_id = row[0]
                        self.stats.texts_created += 1
                        # Add identifier
                        await session.execute(
                            sa_text("""
                                INSERT INTO text_identifiers (text_id, source_id, source_uid)
                                VALUES (:text_id, :source_id, :source_uid)
                                ON CONFLICT (source_id, source_uid) DO NOTHING
                            """),
                            {
                                "text_id": text_id,
                                "source_id": source_id,
                                "source_uid": t["kanripo_id"],
                            },
                        )
                        # Prepare ES doc
                        es_docs.append({
                            "id": text_id,
                            "cbeta_id": t["cbeta_id"],
                            "title_zh": t["title_zh"],
                            "title_sa": t["title_sa"],
                            "translator": t["translator"],
                            "category": t["category"],
                            "fascicle_count": t["fascicle_count"],
                            "lang": "lzh",
                            "source_code": self.SOURCE_CODE,
                        })
                    else:
                        self.stats.skipped += 1

                await session.commit()
                print(f"  Inserted texts batch {i // batch_size + 1} ({min(i + batch_size, len(new_texts))}/{len(new_texts)})")

            # Insert identifier links for existing texts
            for i in range(0, len(identifier_links), batch_size):
                batch = identifier_links[i:i + batch_size]
                for link in batch:
                    await session.execute(
                        sa_text("""
                            INSERT INTO text_identifiers (text_id, source_id, source_uid)
                            VALUES (:text_id, :source_id, :source_uid)
                            ON CONFLICT (source_id, source_uid) DO NOTHING
                        """),
                        {
                            "text_id": link["text_id"],
                            "source_id": source_id,
                            "source_uid": link["kanripo_id"],
                        },
                    )
                await session.commit()
                print(f"  Linked identifiers batch {i // batch_size + 1}")

        # Index to ES
        if es_docs:
            print(f"\n  Indexing {len(es_docs)} docs to ES...")
            from app.core.elasticsearch import INDEX_NAME
            for i in range(0, len(es_docs), batch_size):
                batch = es_docs[i:i + batch_size]
                ops = []
                for doc in batch:
                    doc_id = doc.pop("id")
                    ops.append({"index": {"_index": INDEX_NAME, "_id": str(doc_id)}})
                    ops.append(doc)
                await self.es.bulk(operations=ops, refresh=False)
                print(f"  ES batch {i // batch_size + 1} ({min(i + batch_size, len(es_docs))}/{len(es_docs)})")
            await self.es.indices.refresh(index=INDEX_NAME)
            print("  ES index refreshed")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Import Kanripo Taisho catalog")
    parser.add_argument("--file", default="/tmp/taisho.org", help="Path to taisho.org file")
    parser.add_argument("--download", action="store_true", help="Download fresh copy from GitHub")
    args = parser.parse_args()

    if args.download or not Path(args.file).exists():
        import urllib.request
        url = "https://raw.githubusercontent.com/kanripo/KR-Catalog/master/taisho.org"
        print(f"Downloading from {url}...")
        urllib.request.urlretrieve(url, args.file)
        print(f"Saved to {args.file}")

    importer = KanripoCatalogImporter(catalog_path=args.file)
    asyncio.run(importer.execute())
