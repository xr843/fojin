"""
Import Rangjung Yeshe Tibetan-English Dictionary.

Source: christiansteinert/tibetan-dictionary on GitHub
Contains ~35,000+ Tibetan→English entries in pipe-delimited format.

Usage:
    python scripts/import_rangjung_yeshe.py
    python scripts/import_rangjung_yeshe.py --limit 100
"""

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.base_importer import BaseImporter
from sqlalchemy import text

RY_URL = "https://raw.githubusercontent.com/christiansteinert/tibetan-dictionary/master/_input/dictionaries/public/02-RangjungYeshe"


class RangjungYesheImporter(BaseImporter):
    SOURCE_CODE = "rangjung-yeshe"
    SOURCE_NAME_ZH = "Rangjung Yeshe 藏英辞典"
    SOURCE_NAME_EN = "Rangjung Yeshe Tibetan-English Dictionary"
    SOURCE_BASE_URL = "https://rywiki.tsadra.org"
    SOURCE_DESCRIPTION = "Rangjung Yeshe Tibetan-English Dictionary, via christiansteinert/tibetan-dictionary"
    RATE_LIMIT_DELAY = 0.5

    def __init__(self, limit: int = 0):
        super().__init__()
        self.limit = limit

    async def run_import(self):
        print("  Downloading Rangjung Yeshe dictionary from GitHub...")
        resp = await self.rate_limited_get(RY_URL)
        content = resp.text
        print(f"  Downloaded {len(content)} bytes.")

        lines = content.strip().split("\n")
        # Skip comment lines starting with #
        data_lines = [l for l in lines if l.strip() and not l.startswith("#")]
        print(f"  Found {len(data_lines)} data lines.")

        async with self.session_factory() as session:
            source = await self.ensure_source(session)

            imported = 0
            skipped = 0
            seen = set()

            for line in data_lines:
                # Format: "tibetan_wylie|definition"
                parts = line.split("|", 1)
                if len(parts) < 2:
                    skipped += 1
                    continue

                headword = parts[0].strip()
                definition = parts[1].strip()

                if not headword or not definition:
                    skipped += 1
                    continue

                # Deduplicate by headword (multiple entries possible)
                external_id = f"ry-{headword}"
                if external_id in seen:
                    # Append to existing — but for simplicity, use index-based ID
                    external_id = f"ry-{headword}-{imported}"
                seen.add(external_id)

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
                        "reading": None,
                        "definition": definition,
                        "source_id": source.id,
                        "lang": "bo",
                        "external_id": external_id[:200],
                        "entry_data": None,
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
        self.stats.skipped = skipped
        print(f"  Imported {imported} Rangjung Yeshe entries, skipped {skipped}.")


async def main():
    parser = argparse.ArgumentParser(description="Import Rangjung Yeshe Tibetan-English dictionary")
    parser.add_argument("--limit", type=int, default=0, help="Limit entries")
    args = parser.parse_args()

    importer = RangjungYesheImporter(limit=args.limit)
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
