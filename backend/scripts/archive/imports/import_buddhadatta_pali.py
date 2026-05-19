"""
Import Buddhadatta Pali-Chinese Dictionary from DILA TEI P4 XML.

Source: https://glossaries.dila.edu.tw/glossaries/PLC
Pali→Chinese Buddhist dictionary translated by 達摩比丘.

Note: This dictionary uses TEI P4 format (not P5), so element names
may differ slightly (no namespace prefix).

Usage:
    python scripts/import_buddhadatta_pali.py
    python scripts/import_buddhadatta_pali.py --limit 100
"""

import asyncio
import argparse
import io
import json
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lxml import etree
from scripts.base_importer import BaseImporter
from sqlalchemy import text


class BuddhadattaPaliImporter(BaseImporter):
    """Import Buddhadatta Pali-Chinese dictionary (TEI P4 format)."""

    SOURCE_CODE = "dila-plc"
    SOURCE_NAME_ZH = "巴利語辭典（達摩比丘中譯）"
    SOURCE_NAME_EN = "Buddhadatta Concise Pali-Chinese Dictionary"
    SOURCE_BASE_URL = "https://glossaries.dila.edu.tw/glossaries/PLC"
    SOURCE_DESCRIPTION = "A.P. Buddhadatta 巴英簡明辭典中譯本, 達摩比丘譯, DILA TEI P4 edition"

    ZIP_URL = "https://glossaries.dila.edu.tw/data/pali-chin.dila.tei.p4.xml.zip"
    RATE_LIMIT_DELAY = 0.5

    def __init__(self, limit: int = 0):
        super().__init__()
        self.limit = limit

    def _strip_tags(self, el) -> str:
        return "".join(el.itertext()).strip()

    async def run_import(self):
        print(f"  Downloading pali-chin.dila.tei.p4.xml.zip...")
        resp = await self.rate_limited_get(self.ZIP_URL)
        print(f"  Downloaded {len(resp.content)} bytes.")

        xml_content = None
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            for name in zf.namelist():
                if name.endswith(".xml") and not name.startswith("__MACOSX"):
                    xml_content = zf.read(name)
                    print(f"  Extracted {name} ({len(xml_content)} bytes)")
                    break

        if not xml_content:
            raise RuntimeError("No XML file found in ZIP archive")

        if xml_content.startswith(b"\xef\xbb\xbf"):
            xml_content = xml_content[3:]

        root = etree.fromstring(xml_content)

        # TEI P4 may or may not use namespaces
        # Try with TEI namespace first, then without
        tei_ns = "http://www.tei-c.org/ns/1.0"
        entries = root.findall(f".//{{{tei_ns}}}entry")
        if not entries:
            entries = root.findall(".//entry")
        if not entries:
            entries = root.findall(f".//{{{tei_ns}}}entryFree")
        if not entries:
            entries = root.findall(".//entryFree")

        print(f"  Found {len(entries)} entry elements.")

        if self.limit > 0:
            entries = entries[: self.limit]

        async with self.session_factory() as session:
            source = await self.ensure_source(session)

            imported = 0
            skipped = 0

            for i, entry_el in enumerate(entries):
                # Extract headword — try <form>, <orth>, or direct text
                headword = ""
                for tag in ["form", "orth"]:
                    el = entry_el.find(f"{{{tei_ns}}}{tag}")
                    if el is None:
                        el = entry_el.find(tag)
                    if el is not None:
                        headword = self._strip_tags(el).strip()
                        break

                if not headword:
                    # Try xml:id or n attribute
                    headword = entry_el.get("n", "") or entry_el.get(
                        "{http://www.w3.org/XML/1998/namespace}id", ""
                    )

                if not headword:
                    skipped += 1
                    continue

                # Extract definition
                definition_parts = []
                for tag in ["sense", "def"]:
                    for el in entry_el.findall(f"{{{tei_ns}}}{tag}") or entry_el.findall(tag):
                        t = self._strip_tags(el).strip()
                        if t:
                            definition_parts.append(t)

                if not definition_parts:
                    # Full text fallback
                    full = self._strip_tags(entry_el).strip()
                    if full and full != headword:
                        definition_parts.append(full)

                if not definition_parts:
                    skipped += 1
                    continue

                definition = "\n\n".join(definition_parts)

                await session.execute(
                    text("""
                        INSERT INTO dictionary_entries
                            (headword, reading, definition, source_id, lang, external_id, entry_data)
                        VALUES (:headword, :reading, :definition, :source_id, :lang, :external_id, NULL)
                        ON CONFLICT ON CONSTRAINT uq_dict_entry_source_external DO UPDATE SET
                            headword = EXCLUDED.headword,
                            definition = EXCLUDED.definition
                    """),
                    {
                        "headword": headword[:500],
                        "reading": None,
                        "definition": definition,
                        "source_id": source.id,
                        "lang": "pi",
                        "external_id": f"plc-{i}",
                    },
                )
                imported += 1

                if imported % 5000 == 0:
                    await session.commit()
                    print(f"    ... {imported} entries processed")

            await session.commit()

        self.stats.texts_created = imported
        self.stats.skipped = skipped
        print(f"  Imported {imported} entries, skipped {skipped}.")


async def main():
    parser = argparse.ArgumentParser(description="Import Buddhadatta Pali-Chinese dictionary")
    parser.add_argument("--limit", type=int, default=0, help="Limit entries")
    args = parser.parse_args()

    importer = BuddhadattaPaliImporter(limit=args.limit)
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
