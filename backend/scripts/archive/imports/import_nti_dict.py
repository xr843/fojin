"""
Import NTI Buddhist Text Reader Dictionary (Chinese-English) into dictionary_entries.

Source: https://github.com/alexamies/buddhist-dictionary (CC BY-SA 3.0)
Contains ~48,000 Chinese→English term mappings with pinyin, part of speech, and semantic domains.

Usage:
    python scripts/import_nti_dict.py
    python scripts/import_nti_dict.py --limit 100
"""

import argparse
import asyncio
import csv
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json

from scripts.base_importer import BaseImporter
from sqlalchemy import text

NTI_DICT_URL = "https://raw.githubusercontent.com/alexamies/buddhist-dictionary/master/data/dictionary/cnotes_zh_en_dict.tsv"


class NTIDictImporter(BaseImporter):
    SOURCE_CODE = "nti-reader"
    SOURCE_NAME_ZH = "NTI 汉英佛学辞典"
    SOURCE_NAME_EN = "NTI Buddhist Text Reader Dictionary"
    SOURCE_BASE_URL = "https://ntireader.org"
    SOURCE_DESCRIPTION = "Chinese-English Buddhist dictionary by Fo Guang Shan / Alex Amies (CC BY-SA 3.0)"
    RATE_LIMIT_DELAY = 0.5

    def __init__(self, limit: int = 0):
        super().__init__()
        self.limit = limit

    async def run_import(self):
        print("  Fetching NTI dictionary TSV from GitHub...")
        resp = await self.rate_limited_get(NTI_DICT_URL)
        content = resp.text
        print(f"  Fetched {len(content)} bytes.")

        reader = csv.reader(io.StringIO(content), delimiter="\t")

        # Skip header rows (first 2 lines are headers)
        header = next(reader, None)
        if header and header[0].startswith("#"):
            next(reader, None)  # skip second header line if present

        async with self.session_factory() as session:
            source = await self.ensure_source(session)

            imported = 0
            skipped = 0
            seen = set()

            for row in reader:
                if len(row) < 5:
                    skipped += 1
                    continue

                # TSV columns: id, simplified, traditional, pinyin, english, ...
                row_id = row[0].strip()
                col1 = row[1].strip() if len(row) > 1 else ""
                col2 = row[2].strip() if len(row) > 2 else ""
                pinyin = row[3].strip() if len(row) > 3 else ""
                english = row[4].strip() if len(row) > 4 else ""
                pos = row[5].strip() if len(row) > 5 else ""

                # Handle \N as NULL
                if col2 == "\\N":
                    col2 = ""
                if pinyin == "\\N":
                    pinyin = ""
                if english == "\\N":
                    english = ""
                if pos == "\\N":
                    pos = ""

                # Use traditional form as headword, fall back to simplified
                headword = col1 or col2
                if not headword or not english:
                    skipped += 1
                    continue

                external_id = f"nti-{row_id}"

                # Skip duplicate external_ids (multiple senses get separate rows)
                if external_id in seen:
                    skipped += 1
                    continue
                seen.add(external_id)

                reading = pinyin if pinyin else None

                # Build entry_data with extra metadata
                entry_data = None
                data = {}
                if pos:
                    data["pos"] = pos
                if col2 and col2 != col1:
                    data["traditional"] = col2
                # Semantic domain
                if len(row) > 6 and row[6].strip() and row[6].strip() != "\\N":
                    data["domain_zh"] = row[6].strip()
                if len(row) > 7 and row[7].strip() and row[7].strip() != "\\N":
                    data["domain_en"] = row[7].strip()
                if data:
                    entry_data = json.dumps(data, ensure_ascii=False)

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
                        "headword": headword,
                        "reading": reading,
                        "definition": english,
                        "source_id": source.id,
                        "lang": "zh",
                        "external_id": external_id,
                        "entry_data": entry_data,
                    },
                )
                imported += 1

                if imported % 5000 == 0:
                    await session.commit()
                    print(f"    ... {imported} entries processed")

                if self.limit > 0 and imported >= self.limit:
                    break

            await session.commit()

        self.stats.texts_created = imported
        print(f"  Imported {imported} NTI dictionary entries, skipped {skipped}.")


async def main():
    parser = argparse.ArgumentParser(description="Import NTI Buddhist dictionary")
    parser.add_argument("--limit", type=int, default=0, help="Limit entries")
    args = parser.parse_args()

    importer = NTIDictImporter(limit=args.limit)
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
