"""
Import SuttaCentral Pali glossary into dictionary_entries.

Source: https://suttacentral.net/api/glossary (public, no auth required)
Contains ~5800 Pali→English term mappings.

Usage:
    python scripts/import_sc_glossary.py
    python scripts/import_sc_glossary.py --limit 100
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.base_importer import BaseImporter
from sqlalchemy import text


SC_GLOSSARY_URL = "https://suttacentral.net/api/glossary"


class SCGlossaryImporter(BaseImporter):
    SOURCE_CODE = "suttacentral"
    SOURCE_NAME_ZH = "SuttaCentral 巴利经藏"
    SOURCE_NAME_EN = "SuttaCentral"
    SOURCE_BASE_URL = "https://suttacentral.net"
    SOURCE_DESCRIPTION = "Early Buddhist texts, translations, and parallels"
    RATE_LIMIT_DELAY = 0.5

    def __init__(self, limit: int = 0):
        super().__init__()
        self.limit = limit

    async def run_import(self):
        print("  Fetching SuttaCentral glossary...")
        resp = await self.rate_limited_get(SC_GLOSSARY_URL)
        entries = resp.json()
        print(f"  Fetched {len(entries)} glossary entries.")

        if self.limit > 0:
            entries = entries[:self.limit]

        async with self.session_factory() as session:
            source = await self.ensure_source(session)

            imported = 0
            skipped = 0
            for entry in entries:
                headword = entry.get("entry", "").strip()
                gloss = entry.get("gloss", "").strip()
                if not headword or not gloss:
                    skipped += 1
                    continue

                external_id = f"sc-glossary-{headword}"

                await session.execute(
                    text("""
                        INSERT INTO dictionary_entries
                            (headword, reading, definition, source_id, lang, external_id)
                        VALUES (:headword, NULL, :definition, :source_id, :lang, :external_id)
                        ON CONFLICT ON CONSTRAINT uq_dict_entry_source_external DO UPDATE SET
                            headword = EXCLUDED.headword,
                            definition = EXCLUDED.definition
                    """),
                    {
                        "headword": headword,
                        "definition": gloss,
                        "source_id": source.id,
                        "lang": "pi",
                        "external_id": external_id,
                    },
                )
                imported += 1

            await session.commit()

        self.stats.texts_created = imported
        print(f"  Imported {imported} Pali glossary entries, skipped {skipped}.")


async def main():
    parser = argparse.ArgumentParser(description="Import SuttaCentral Pali glossary")
    parser.add_argument("--limit", type=int, default=0, help="Limit entries")
    args = parser.parse_args()

    importer = SCGlossaryImporter(limit=args.limit)
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
