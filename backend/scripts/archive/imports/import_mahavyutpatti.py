"""
Import Mahāvyutpatti (翻譯名義大集) from DILA TEI P5 XML.

Source: https://glossaries.dila.edu.tw/glossaries/MVP
Sanskrit-Tibetan-Chinese Buddhist terminology collection.

Usage:
    python scripts/import_mahavyutpatti.py
    python scripts/import_mahavyutpatti.py --limit 100
"""

import asyncio
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.import_dila_dict import DilaBaseImporter, TEI_NS


class MahavyutpattiImporter(DilaBaseImporter):
    SOURCE_CODE = "dila-mvp"
    SOURCE_NAME_ZH = "翻譯名義大集"
    SOURCE_NAME_EN = "Mahāvyutpatti (Sanskrit-Tibetan-Chinese)"
    SOURCE_BASE_URL = "https://glossaries.dila.edu.tw/glossaries/MVP"
    SOURCE_DESCRIPTION = "翻譯名義大集 (Mahāvyutpatti), 梵藏漢佛教術語對照, DILA TEI P5 edition"

    DILA_ZIP_FILENAME = "mahavyutpatti.dila.tei.p5.xml.zip"
    DICT_LANG = "sa"

    def parse_entry(self, entry_el, index: int) -> dict | None:
        """
        MVP format — entries typically have multilingual <form> and <sense>.
        We extract Sanskrit headword + Tibetan/Chinese translations.
        """
        # Try to get headword from <form>
        form_el = entry_el.find(f"{{{TEI_NS}}}form")
        if form_el is None:
            form_el = entry_el.find("form")

        headword = ""
        if form_el is not None:
            headword = self._strip_tags(form_el).strip()

        if not headword:
            # Try xml:id as fallback
            xml_id = entry_el.get("{http://www.w3.org/XML/1998/namespace}id", "")
            if xml_id:
                headword = xml_id
            else:
                return None

        # Extract all text content from senses
        parts = []
        entry_data = {}

        for sense_el in entry_el.findall(f"{{{TEI_NS}}}sense") or entry_el.findall("sense"):
            sense_text = self._strip_tags(sense_el).strip()
            if sense_text:
                parts.append(sense_text)

            # Extract language-specific terms
            for cit_el in sense_el.findall(f"{{{TEI_NS}}}cit") or sense_el.findall("cit"):
                lang = cit_el.get("{http://www.w3.org/XML/1998/namespace}lang", "")
                quote_el = cit_el.find(f"{{{TEI_NS}}}quote")
                if quote_el is None:
                    quote_el = cit_el.find("quote")
                if quote_el is not None:
                    text = self._strip_tags(quote_el).strip()
                    if text:
                        if "bod" in lang or "tib" in lang:
                            entry_data["tibetan"] = text
                        elif "chi" in lang or "zho" in lang:
                            entry_data["chinese"] = text

        # If no sense content, try full entry text
        if not parts:
            full_text = self._strip_tags(entry_el).strip()
            if full_text and full_text != headword:
                parts.append(full_text)

        definition = "\n\n".join(parts)
        if not definition:
            return None

        return {
            "headword": headword,
            "reading": None,
            "definition": definition,
            "external_id": f"mvp-{index}",
            "entry_data": entry_data if entry_data else None,
        }


async def main():
    parser = argparse.ArgumentParser(description="Import Mahāvyutpatti dictionary")
    parser.add_argument("--limit", type=int, default=0, help="Limit entries")
    args = parser.parse_args()

    importer = MahavyutpattiImporter(limit=args.limit)
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
