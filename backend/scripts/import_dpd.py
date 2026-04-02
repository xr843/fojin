"""
Import Digital Pali Dictionary (DPD) from SQLite database.

Source: https://github.com/digitalpalidictionary/dpd-db
Contains ~83,000 Pali headword entries with English definitions,
grammar info, Sanskrit equivalents, and usage examples.

Usage:
    python scripts/import_dpd.py --file /path/to/dpd.db
    python scripts/import_dpd.py --file /path/to/dpd.db --limit 100
    python scripts/import_dpd.py --download   # auto-download latest release
"""

import argparse
import asyncio
import json
import os
import sqlite3
import sys
import tarfile
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.base_importer import BaseImporter
from sqlalchemy import text

DPD_RELEASE_URL = "https://github.com/digitalpalidictionary/dpd-db/releases/latest/download/dpd.db.tar.bz2"


class DpdImporter(BaseImporter):
    SOURCE_CODE = "dpd"
    SOURCE_NAME_ZH = "Digital Pali Dictionary"
    SOURCE_NAME_EN = "Digital Pali Dictionary (DPD)"
    SOURCE_BASE_URL = "https://dpdict.net/"
    SOURCE_DESCRIPTION = "Digital Pali Dictionary — 巴利語數字辭典，含語法、詞根、梵語對照 (CC BY-NC-SA 4.0)"
    RATE_LIMIT_DELAY = 0

    def __init__(self, db_path: str, limit: int = 0):
        super().__init__()
        self.db_path = db_path
        self.limit = limit

    async def run_import(self):
        print(f"  Opening DPD database: {self.db_path}")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        # Query only needed columns for efficiency
        query = """SELECT id, lemma_1, lemma_2, pos, grammar,
                          meaning_1, meaning_2, meaning_lit,
                          construction, sanskrit, root_key, root_base,
                          example_1, sutta_1
                   FROM dpd_headwords ORDER BY id"""
        if self.limit > 0:
            query += f" LIMIT {self.limit}"

        rows = conn.execute(query).fetchall()
        print(f"  Found {len(rows)} headword entries.")

        async with self.session_factory() as session:
            source = await self.ensure_source(session)

            imported = 0
            skipped = 0

            for row in rows:
                # Headword: use lemma_1, strip numeric suffix like "dhamma 1.01"
                lemma = row["lemma_1"] or ""
                headword = lemma.split(" ")[0] if " " in lemma else lemma
                if not headword:
                    skipped += 1
                    continue

                # Build definition from meaning fields
                def_parts = []
                pos = row["pos"] or ""
                grammar = row["grammar"] or ""

                if pos:
                    def_parts.append(f"({pos})" if not grammar else f"({pos}, {grammar})")

                meaning_1 = row["meaning_1"] or ""
                meaning_2 = row["meaning_2"] or ""
                meaning_lit = row["meaning_lit"] or ""

                if meaning_1:
                    def_parts.append(meaning_1)
                if meaning_2:
                    def_parts.append(meaning_2)
                if meaning_lit:
                    def_parts.append(f"[lit.] {meaning_lit}")

                construction = row["construction"] or ""
                if construction:
                    def_parts.append(f"Construction: {construction}")

                definition = "\n".join(def_parts)
                if not definition:
                    skipped += 1
                    continue

                # Entry data with additional info
                entry_data = {}
                sanskrit = row["sanskrit"] or ""
                if sanskrit:
                    entry_data["sanskrit"] = sanskrit

                root_key = row["root_key"] or ""
                if root_key:
                    entry_data["root"] = root_key

                root_base = row["root_base"] or ""
                if root_base:
                    entry_data["root_base"] = root_base

                example_1 = row["example_1"] or ""
                if example_1:
                    entry_data["example"] = example_1

                sutta_1 = row["sutta_1"] or ""
                if sutta_1:
                    entry_data["source"] = sutta_1

                entry_data_json = json.dumps(entry_data, ensure_ascii=False) if entry_data else None

                await session.execute(
                    text("""
                        INSERT INTO dictionary_entries
                            (headword, reading, definition, source_id, lang, external_id, entry_data)
                        VALUES (:headword, :reading, :definition, :source_id, :lang, :external_id,
                                CAST(:entry_data AS jsonb))
                        ON CONFLICT ON CONSTRAINT uq_dict_entry_source_external DO UPDATE SET
                            headword = EXCLUDED.headword,
                            reading = EXCLUDED.reading,
                            definition = EXCLUDED.definition,
                            entry_data = EXCLUDED.entry_data
                    """),
                    {
                        "headword": headword[:500],
                        "reading": lemma if lemma != headword else None,
                        "definition": definition,
                        "source_id": source.id,
                        "lang": "pi",
                        "external_id": f"dpd-{row['id']}",
                        "entry_data": entry_data_json,
                    },
                )
                imported += 1

                if imported % 5000 == 0:
                    await session.commit()
                    print(f"    ... {imported}/{len(rows)} entries processed")

            await session.commit()

        conn.close()
        self.stats.texts_created = imported
        self.stats.skipped = skipped
        print(f"  Imported {imported} entries, skipped {skipped}.")


def download_dpd(dest_dir: str) -> str:
    """Download and extract DPD SQLite database."""
    import httpx

    tar_path = os.path.join(dest_dir, "dpd.db.tar.bz2")
    db_path = os.path.join(dest_dir, "dpd.db")

    if os.path.exists(db_path):
        print(f"  DPD database already exists at {db_path}")
        return db_path

    print(f"  Downloading DPD from {DPD_RELEASE_URL}...")
    with httpx.Client(follow_redirects=True, timeout=300) as client:
        resp = client.get(DPD_RELEASE_URL)
        resp.raise_for_status()
        with open(tar_path, "wb") as f:
            f.write(resp.content)
        print(f"  Downloaded {len(resp.content) / 1024 / 1024:.1f} MB")

    print(f"  Extracting...")
    with tarfile.open(tar_path, "r:bz2") as tar:
        tar.extractall(path=dest_dir)

    if os.path.exists(db_path):
        os.remove(tar_path)
        print(f"  Extracted to {db_path}")
        return db_path

    # Find the extracted .db file
    for f in os.listdir(dest_dir):
        if f.endswith(".db"):
            result = os.path.join(dest_dir, f)
            os.remove(tar_path)
            return result

    raise RuntimeError("Could not find dpd.db after extraction")


async def main():
    parser = argparse.ArgumentParser(description="Import Digital Pali Dictionary")
    parser.add_argument("--file", type=str, help="Path to dpd.db SQLite file")
    parser.add_argument("--download", action="store_true", help="Auto-download latest DPD release")
    parser.add_argument("--limit", type=int, default=0, help="Limit entries (0 = all)")
    args = parser.parse_args()

    if args.download:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        os.makedirs(data_dir, exist_ok=True)
        db_path = download_dpd(data_dir)
    elif args.file:
        db_path = args.file
        if not os.path.exists(db_path):
            print(f"ERROR: File not found: {db_path}")
            sys.exit(1)
    else:
        print("ERROR: Provide --file or --download")
        sys.exit(1)

    importer = DpdImporter(db_path=db_path, limit=args.limit)
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
