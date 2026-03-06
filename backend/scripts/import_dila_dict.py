"""
Base importer for DILA TEI P5 XML dictionaries.

Handles downloading ZIP from glossaries.dila.edu.tw, extracting XML,
and parsing TEI P5 <entry> elements. Subclasses override parse_entry()
for dictionary-specific field extraction.

Usage: Subclass DilaBaseImporter and implement parse_entry().
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

from lxml import etree
from scripts.base_importer import BaseImporter
from sqlalchemy import text

TEI_NS = "http://www.tei-c.org/ns/1.0"
NSMAP = {"tei": TEI_NS}


class DilaBaseImporter(BaseImporter):
    """Base class for DILA TEI P5 dictionary importers."""

    # Subclass must set these
    DILA_ZIP_FILENAME: str = ""  # e.g. "soothill-hodous.ddbc.tei.p5.xml.zip"
    DILA_BASE_URL = "https://glossaries.dila.edu.tw/data"
    DICT_LANG: str = "zh"  # headword language
    RATE_LIMIT_DELAY = 0.5

    def __init__(self, limit: int = 0):
        super().__init__()
        self.limit = limit

    @property
    def zip_url(self) -> str:
        return f"{self.DILA_BASE_URL}/{self.DILA_ZIP_FILENAME}"

    def _strip_tags(self, el) -> str:
        """Extract all text content from an lxml element, stripping tags."""
        return "".join(el.itertext()).strip()

    def _strip_tags_str(self, s: str) -> str:
        """Remove XML/HTML tags from a string and normalize whitespace."""
        clean = re.sub(r"<[^>]+>", " ", s)
        return re.sub(r"\s+", " ", clean).strip()

    def parse_entry(self, entry_el, index: int) -> dict | None:
        """
        Parse a single <entry> element into a dict with keys:
            headword, reading, definition, external_id, entry_data (dict or None)

        Return None to skip the entry.
        Subclasses should override this method.
        """
        raise NotImplementedError

    async def run_import(self):
        print(f"  Downloading {self.DILA_ZIP_FILENAME}...")
        resp = await self.rate_limited_get(self.zip_url)
        print(f"  Downloaded {len(resp.content)} bytes.")

        # Extract XML from ZIP
        xml_content = None
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            for name in zf.namelist():
                if name.endswith(".xml") and not name.startswith("__MACOSX"):
                    xml_content = zf.read(name)
                    print(f"  Extracted {name} ({len(xml_content)} bytes)")
                    break

        if not xml_content:
            raise RuntimeError("No XML file found in ZIP archive")

        # Parse XML with lxml — remove BOM if present
        if xml_content.startswith(b"\xef\xbb\xbf"):
            xml_content = xml_content[3:]
        root = etree.fromstring(xml_content)

        # Find all <entry> elements (with or without namespace)
        entries = root.findall(f".//{{{TEI_NS}}}entry")
        if not entries:
            entries = root.findall(".//entry")
        print(f"  Found {len(entries)} <entry> elements.")

        if self.limit > 0:
            entries = entries[: self.limit]

        async with self.session_factory() as session:
            source = await self.ensure_source(session)

            imported = 0
            skipped = 0

            for i, entry_el in enumerate(entries):
                try:
                    parsed = self.parse_entry(entry_el, i)
                except Exception as e:
                    self.stats.errors += 1
                    if self.stats.errors <= 5:
                        print(f"  Error parsing entry {i}: {e}")
                    continue

                if parsed is None:
                    skipped += 1
                    continue

                headword = parsed["headword"]
                if not headword:
                    skipped += 1
                    continue

                external_id = parsed.get("external_id", f"{self.SOURCE_CODE}-{i}")
                entry_data = parsed.get("entry_data")
                entry_data_json = (
                    json.dumps(entry_data, ensure_ascii=False) if entry_data else None
                )

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
                        "reading": (parsed.get("reading") or "")[:500] or None,
                        "definition": parsed.get("definition"),
                        "source_id": source.id,
                        "lang": self.DICT_LANG,
                        "external_id": external_id,
                        "entry_data": entry_data_json,
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
