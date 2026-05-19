"""
Import Edgerton's Buddhist Hybrid Sanskrit Dictionary from Cologne Digital Sanskrit Lexicon.

Source: https://www.sanskrit-lexicon.uni-koeln.de (CC BY-NC-SA 3.0)
Contains ~17,800 Buddhist Hybrid Sanskrit→English entries.

Downloads XML archive from Cologne, parses locally.

Usage:
    python scripts/import_edgerton_bhs.py
    python scripts/import_edgerton_bhs.py --limit 100
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

BHS_ZIP_URL = "https://www.sanskrit-lexicon.uni-koeln.de/scans/BHSScan/2020/downloads/bhsxml.zip"


class EdgertonBHSImporter(BaseImporter):
    SOURCE_CODE = "cdsl-bhs"
    SOURCE_NAME_ZH = "Edgerton 佛教混合梵语辞典"
    SOURCE_NAME_EN = "Buddhist Hybrid Sanskrit Dictionary (Edgerton)"
    SOURCE_BASE_URL = "https://www.sanskrit-lexicon.uni-koeln.de"
    SOURCE_DESCRIPTION = "Edgerton's Buddhist Hybrid Sanskrit Grammar and Dictionary, Cologne Digital Sanskrit Lexicon (CC BY-NC-SA 3.0)"
    RATE_LIMIT_DELAY = 0.5

    def __init__(self, limit: int = 0):
        super().__init__()
        self.limit = limit

    def _strip_tags(self, s: str) -> str:
        """Remove XML/HTML tags and normalize whitespace."""
        clean = re.sub(r"<[^>]+>", " ", s)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    def _parse_entries(self, xml_content: str) -> list:
        """Parse BHS XML into list of (key, headword, definition, page) tuples."""
        entries = []
        # Match H1 entries (main headword entries)
        pattern = re.compile(
            r'<H1><h><key1>([^<]+)</key1><key2>([^<]+)</key2>'
            r'(?:<hom>(\d+)</hom>)?'
            r'</h><body>(.*?)</body>'
            r'<tail><L>(\d+)</L><pc>([^<]+)</pc></tail></H1>',
            re.DOTALL,
        )
        for m in pattern.finditer(xml_content):
            key1 = m.group(1)
            key2 = m.group(2)
            hom = m.group(3) or ""
            body = m.group(4)
            lemma_id = m.group(5)
            page = m.group(6)

            # Extract readable headword from body (first <b> tag)
            hw_match = re.search(r"<b>([^<]+)</b>", body)
            headword = hw_match.group(1).strip() if hw_match else self._strip_tags(key2)

            definition = self._strip_tags(body)
            if not definition:
                continue

            entry_id = f"{lemma_id}"
            if hom:
                entry_id = f"{lemma_id}_{hom}"

            entries.append((entry_id, headword, definition, page, key1))

        return entries

    async def run_import(self):
        print("  Downloading BHS XML archive from Cologne...")
        resp = await self.rate_limited_get(BHS_ZIP_URL)
        print(f"  Downloaded {len(resp.content)} bytes.")

        # Extract XML from zip
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            xml_filename = [n for n in zf.namelist() if n.endswith(".xml") and "header" not in n][0]
            xml_content = zf.read(xml_filename).decode("utf-8")
            print(f"  Extracted {xml_filename} ({len(xml_content)} chars)")

        entries = self._parse_entries(xml_content)
        print(f"  Parsed {len(entries)} BHS entries.")

        if self.limit > 0:
            entries = entries[:self.limit]

        async with self.session_factory() as session:
            source = await self.ensure_source(session)

            imported = 0
            skipped = 0
            for entry_id, headword, definition, page, slp1 in entries:
                if not headword or not definition:
                    skipped += 1
                    continue

                external_id = f"bhs-{entry_id}"

                entry_data = json.dumps({
                    "slp1": slp1,
                    "page": page,
                }, ensure_ascii=False)

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
                        "reading": slp1 if slp1 != headword else None,
                        "definition": definition,
                        "source_id": source.id,
                        "lang": "sa",
                        "external_id": external_id,
                        "entry_data": entry_data,
                    },
                )
                imported += 1

                if imported % 5000 == 0:
                    await session.commit()
                    print(f"    ... {imported} entries processed")

            await session.commit()

        self.stats.texts_created = imported
        print(f"  Imported {imported} BHS entries, skipped {skipped}.")


async def main():
    parser = argparse.ArgumentParser(description="Import Edgerton BHS dictionary")
    parser.add_argument("--limit", type=int, default=0, help="Limit entries")
    args = parser.parse_args()

    importer = EdgertonBHSImporter(limit=args.limit)
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
