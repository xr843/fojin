"""
Import SuttaCentral NCPED (New Concise Pali-English Dictionary) into dictionary_entries.

Source: https://github.com/suttacentral/sc-data (CC0)
Based on Buddhadatta's Concise Pali-English Dictionary, updated from Margaret Cone.
Contains ~8000 Pali→English term mappings with grammar info.

Usage:
    python scripts/import_ncped.py
    python scripts/import_ncped.py --limit 100
"""

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.base_importer import BaseImporter
from sqlalchemy import text

NCPED_URL = "https://raw.githubusercontent.com/suttacentral/sc-data/main/dictionaries/simple/en/pli2en_ncped.json"
NCPED_URL_FALLBACK = "https://raw.githubusercontent.com/suttacentral/sc-data/master/dictionaries/simple/en/pli2en_ncped.json"


class NCPEDImporter(BaseImporter):
    SOURCE_CODE = "ncped"
    SOURCE_NAME_ZH = "NCPED 巴英简明辞典"
    SOURCE_NAME_EN = "New Concise Pali-English Dictionary"
    SOURCE_BASE_URL = "https://suttacentral.net"
    SOURCE_DESCRIPTION = "Buddhadatta's Concise Pali-English Dictionary, updated from Margaret Cone (CC0)"
    RATE_LIMIT_DELAY = 0.5

    def __init__(self, limit: int = 0):
        super().__init__()
        self.limit = limit

    async def run_import(self):
        print("  Fetching NCPED dictionary from sc-data...")
        try:
            resp = await self.rate_limited_get(NCPED_URL)
        except Exception:
            print("  Main branch URL failed, trying master...")
            resp = await self.rate_limited_get(NCPED_URL_FALLBACK)

        entries = resp.json()
        print(f"  Fetched {len(entries)} NCPED entries.")

        if self.limit > 0:
            entries = entries[:self.limit]

        async with self.session_factory() as session:
            source = await self.ensure_source(session)

            imported = 0
            skipped = 0
            for entry in entries:
                headword = entry.get("entry", "").strip()
                if not headword:
                    skipped += 1
                    continue

                # definition can be string or list
                raw_def = entry.get("definition", "")
                if isinstance(raw_def, list):
                    definition = "; ".join(str(d) for d in raw_def)
                else:
                    definition = str(raw_def).strip()

                if not definition:
                    skipped += 1
                    continue

                grammar = entry.get("grammar", "")

                # Build reading from grammar info
                reading = grammar if grammar else None

                # Store cross-references in entry_data
                xr = entry.get("xr")
                entry_data = None
                if xr or grammar:
                    data = {}
                    if grammar:
                        data["grammar"] = grammar
                    if xr:
                        data["xr"] = xr if isinstance(xr, list) else [xr]
                    entry_data = json.dumps(data, ensure_ascii=False)

                external_id = f"ncped-{headword}"

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
                        "definition": definition,
                        "source_id": source.id,
                        "lang": "pi",
                        "external_id": external_id,
                        "entry_data": entry_data,
                    },
                )
                imported += 1

                if imported % 2000 == 0:
                    await session.commit()
                    print(f"    ... {imported} entries processed")

            await session.commit()

        self.stats.texts_created = imported
        print(f"  Imported {imported} NCPED entries, skipped {skipped}.")


async def main():
    parser = argparse.ArgumentParser(description="Import NCPED Pali-English dictionary")
    parser.add_argument("--limit", type=int, default=0, help="Limit entries")
    args = parser.parse_args()

    importer = NCPEDImporter(limit=args.limit)
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
