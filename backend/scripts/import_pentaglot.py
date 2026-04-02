"""
Import Pentaglot Dictionary of Buddhist Terms (五體清文鑑佛教部分) from DILA TEI P5 XML.

Source: https://glossaries.dila.edu.tw/glossaries/PTG
Manchu-Mongolian-Tibetan-Chinese-Sanskrit five-language Buddhist dictionary.

Usage:
    python scripts/import_pentaglot.py
    python scripts/import_pentaglot.py --limit 100
"""

import asyncio
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.import_dila_dict import DilaBaseImporter, TEI_NS


class PentaglotImporter(DilaBaseImporter):
    SOURCE_CODE = "dila-ptg"
    SOURCE_NAME_ZH = "五體清文鑑（佛教部分）"
    SOURCE_NAME_EN = "Pentaglot Dictionary of Buddhist Terms"
    SOURCE_BASE_URL = "https://glossaries.dila.edu.tw/glossaries/PTG"
    SOURCE_DESCRIPTION = "五體清文鑑佛教部分, 滿蒙藏漢梵五語佛教術語辭典, DILA TEI P5 edition"

    DILA_ZIP_FILENAME = "pentaglot.dila.tei.p5.xml.zip"
    DICT_LANG = "zh"

    def parse_entry(self, entry_el, index: int) -> dict | None:
        form_el = entry_el.find(f"{{{TEI_NS}}}form")
        if form_el is None:
            form_el = entry_el.find("form")
        if form_el is None:
            return None

        headword = self._strip_tags(form_el).strip()
        if not headword:
            return None

        # Collect all sense/definition text
        parts = []
        entry_data = {}

        for sense_el in entry_el.findall(f"{{{TEI_NS}}}sense") or entry_el.findall("sense"):
            sense_text = self._strip_tags(sense_el).strip()
            if sense_text:
                parts.append(sense_text)

            # Extract language-tagged terms
            for cit_el in sense_el.findall(f"{{{TEI_NS}}}cit") or sense_el.findall("cit"):
                lang = cit_el.get("{http://www.w3.org/XML/1998/namespace}lang", "")
                quote_el = cit_el.find(f"{{{TEI_NS}}}quote")
                if quote_el is None:
                    quote_el = cit_el.find("quote")
                if quote_el is not None:
                    text = self._strip_tags(quote_el).strip()
                    if text:
                        if "san" in lang:
                            entry_data["sanskrit"] = text
                        elif "bod" in lang or "tib" in lang:
                            entry_data["tibetan"] = text
                        elif "mon" in lang:
                            entry_data["mongolian"] = text
                        elif "mnc" in lang:
                            entry_data["manchu"] = text

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
            "external_id": f"ptg-{index}",
            "entry_data": entry_data if entry_data else None,
        }


async def main():
    parser = argparse.ArgumentParser(description="Import Pentaglot dictionary")
    parser.add_argument("--limit", type=int, default=0, help="Limit entries")
    args = parser.parse_args()

    importer = PentaglotImporter(limit=args.limit)
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
