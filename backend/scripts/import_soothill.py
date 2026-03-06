"""
Import Soothill-Hodous Chinese Buddhist Terms Dictionary from DILA TEI P5 XML.

Source: https://glossaries.dila.edu.tw/glossaries/SHH (Creative Commons)
Contains ~16,800 Chinese→English Buddhist term entries.

Usage:
    python scripts/import_soothill.py
    python scripts/import_soothill.py --limit 100
"""

import asyncio
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.import_dila_dict import DilaBaseImporter, TEI_NS


class SoothillImporter(DilaBaseImporter):
    SOURCE_CODE = "dila-soothill"
    SOURCE_NAME_ZH = "Soothill 中英佛学辞典"
    SOURCE_NAME_EN = "Soothill-Hodous Dictionary of Chinese Buddhist Terms"
    SOURCE_BASE_URL = "https://glossaries.dila.edu.tw/glossaries/SHH"
    SOURCE_DESCRIPTION = "Soothill & Hodous, A Dictionary of Chinese Buddhist Terms (1937), DILA TEI P5 edition"

    DILA_ZIP_FILENAME = "soothill-hodous.ddbc.tei.p5.xml.zip"
    DICT_LANG = "zh"

    def parse_entry(self, entry_el, index: int) -> dict | None:
        """
        Soothill format:
        <entry>
          <form>词头</form>
          <sense>
            <term xml:lang="san-Latn">Sanskrit</term>. English definition text.
          </sense>
        </entry>
        No xml:id. Definition is inline text in <sense>, may contain <term> for Sanskrit.
        """
        # Extract headword from <form>
        form_el = entry_el.find(f"{{{TEI_NS}}}form")
        if form_el is None:
            form_el = entry_el.find("form")
        if form_el is None:
            return None

        headword = self._strip_tags(form_el).strip()
        if not headword:
            return None

        # Extract definition from <sense> — full text content
        sense_el = entry_el.find(f"{{{TEI_NS}}}sense")
        if sense_el is None:
            sense_el = entry_el.find("sense")
        if sense_el is None:
            return None

        definition = self._strip_tags(sense_el).strip()
        if not definition:
            return None

        # Extract Sanskrit terms if present
        entry_data = None
        sanskrit_terms = []
        term_els = sense_el.findall(f"{{{TEI_NS}}}term")
        if not term_els:
            term_els = sense_el.findall("term")
        for term_el in term_els:
            lang = term_el.get("{http://www.w3.org/XML/1998/namespace}lang", "")
            term_text = self._strip_tags(term_el).strip()
            if term_text and "san" in lang:
                sanskrit_terms.append(term_text)

        if sanskrit_terms:
            entry_data = {"sanskrit": sanskrit_terms if len(sanskrit_terms) > 1 else sanskrit_terms[0]}

        return {
            "headword": headword,
            "reading": None,
            "definition": definition,
            "external_id": f"shh-{index}",
            "entry_data": entry_data,
        }


async def main():
    parser = argparse.ArgumentParser(description="Import Soothill-Hodous dictionary")
    parser.add_argument("--limit", type=int, default=0, help="Limit entries")
    args = parser.parse_args()

    importer = SoothillImporter(limit=args.limit)
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
