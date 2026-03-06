"""
Import PTS Pāli-English Dictionary from vpnry/ptsped GitHub tabfile.

Source: https://github.com/vpnry/ptsped (CC BY-NC 3.0, © Pali Text Society)
Contains ~15,700 Pāli→English entries.

Usage:
    python scripts/import_pts_pali.py
    python scripts/import_pts_pali.py --limit 100
"""

import argparse
import asyncio
import io
import json
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.base_importer import BaseImporter
from sqlalchemy import text

PTS_ZIP_URL = "https://raw.githubusercontent.com/vpnry/ptsped/master/tabfiles/Tabfile_PTSPED-2021.zip"


class PTSPaliImporter(BaseImporter):
    SOURCE_CODE = "pts-ped"
    SOURCE_NAME_ZH = "PTS 巴英辞典"
    SOURCE_NAME_EN = "PTS Pāli-English Dictionary"
    SOURCE_BASE_URL = "https://www.palitext.com"
    SOURCE_DESCRIPTION = "The Pali Text Society's Pāli-English Dictionary, Rhys Davids & Stede (CC BY-NC 3.0)"
    RATE_LIMIT_DELAY = 0.5

    def __init__(self, limit: int = 0):
        super().__init__()
        self.limit = limit

    def _strip_html(self, s: str) -> str:
        """Remove HTML tags and normalize whitespace."""
        # Remove HTML tags
        clean = re.sub(r"<[^>]+>", " ", s)
        # Normalize whitespace
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    def _clean_headword(self, hw: str) -> str:
        """Clean headword: remove numbering prefixes like '000License', '001info'."""
        # Remove leading digits used for ordering
        hw = re.sub(r"^\d+", "", hw).strip()
        return hw

    async def run_import(self):
        print("  Downloading PTS PED tabfile from GitHub...")
        resp = await self.rate_limited_get(PTS_ZIP_URL)
        print(f"  Downloaded {len(resp.content)} bytes.")

        # Extract tabfile from ZIP
        tab_content = None
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            for name in zf.namelist():
                if not name.startswith("__MACOSX"):
                    tab_content = zf.read(name).decode("utf-8")
                    print(f"  Extracted {name} ({len(tab_content)} chars)")
                    break

        if not tab_content:
            raise RuntimeError("No tabfile found in ZIP archive")

        lines = tab_content.strip().split("\n")
        print(f"  Found {len(lines)} lines.")

        async with self.session_factory() as session:
            source = await self.ensure_source(session)

            imported = 0
            skipped = 0

            for line in lines:
                parts = line.split("\t", 1)
                if len(parts) < 2:
                    skipped += 1
                    continue

                raw_headword = parts[0].strip()
                raw_definition = parts[1].strip()

                # Skip metadata entries (000License, 001info, 002info)
                if re.match(r"^\d{3}(License|info)", raw_headword):
                    skipped += 1
                    continue

                headword = self._clean_headword(raw_headword)
                if not headword:
                    skipped += 1
                    continue

                # Strip HTML from definition but keep readable text
                definition = self._strip_html(raw_definition)
                if not definition:
                    skipped += 1
                    continue

                external_id = f"pts-{raw_headword}"

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
                        "lang": "pi",
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
        print(f"  Imported {imported} PTS PED entries, skipped {skipped}.")


async def main():
    parser = argparse.ArgumentParser(description="Import PTS Pāli-English Dictionary")
    parser.add_argument("--limit", type=int, default=0, help="Limit entries")
    args = parser.parse_args()

    importer = PTSPaliImporter(limit=args.limit)
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
