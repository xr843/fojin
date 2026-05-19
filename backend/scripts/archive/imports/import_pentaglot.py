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
        """
        PTG format — no <form>, languages are in <sense xml:lang="...">:
        <entry xml:id="p005.2">
            <sense xml:lang="san-Latn">buddhaḥ</sense>
            <sense xml:lang="bod-Tibt"/>
            <sense xml:lang="mnc-Latn">fucihi</sense>
            <sense xml:lang="mon-Latn">burkhan</sense>
            <sense xml:lang="zho-Hant">佛</sense>
        </entry>
        Use Chinese as headword, Sanskrit as reading, build multilingual definition.
        """
        XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
        senses = entry_el.findall(f"{{{TEI_NS}}}sense")
        if not senses:
            senses = entry_el.findall("sense")

        langs = {}
        for sense_el in senses:
            lang = sense_el.get(XML_LANG, "") or sense_el.get("lang", "")
            text = self._strip_tags(sense_el).strip()
            if text:
                langs[lang] = text

        # Chinese headword
        headword = langs.get("zho-Hant", "") or langs.get("zho-Hans", "") or langs.get("zho", "")
        if not headword:
            # Fallback: use Sanskrit
            headword = langs.get("san-Latn", "") or langs.get("san", "")
        if not headword:
            return None

        # Build definition showing all languages
        def_parts = []
        entry_data = {}
        lang_labels = {
            "san-Latn": ("梵", "sanskrit"),
            "bod-Tibt": ("藏", "tibetan"),
            "mnc-Latn": ("滿", "manchu"),
            "mon-Latn": ("蒙", "mongolian"),
            "zho-Hant": ("漢", None),
        }
        for lang_code, (label, data_key) in lang_labels.items():
            val = langs.get(lang_code, "")
            if val and val != headword:
                def_parts.append(f"{label}: {val}")
            if val and data_key:
                entry_data[data_key] = val

        definition = "\n".join(def_parts) if def_parts else langs.get("san-Latn", "")
        if not definition:
            return None

        xml_id = entry_el.get("{http://www.w3.org/XML/1998/namespace}id", "") or entry_el.get("id", "")
        external_id = f"ptg-{xml_id}" if xml_id else f"ptg-{index}"

        return {
            "headword": headword,
            "reading": langs.get("san-Latn"),
            "definition": definition,
            "external_id": external_id,
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
