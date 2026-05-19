"""
Import 丁福保《佛学大辞典》from DILA TEI P5 XML.

Source: https://glossaries.dila.edu.tw/glossaries/DFB (CC BY-SA 2.5 TW)
Contains ~31,000 Chinese→Chinese Buddhist dictionary entries.

Usage:
    python scripts/import_dingfubao.py
    python scripts/import_dingfubao.py --limit 100
"""

import asyncio
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.import_dila_dict import DilaBaseImporter, TEI_NS


class DingFuBaoImporter(DilaBaseImporter):
    SOURCE_CODE = "dila-dfb"
    SOURCE_NAME_ZH = "丁福保佛学大辞典"
    SOURCE_NAME_EN = "Ding Fubao Dictionary of Buddhist Studies"
    SOURCE_BASE_URL = "https://glossaries.dila.edu.tw/glossaries/DFB"
    SOURCE_DESCRIPTION = "丁福保《佛学大辞典》, DILA TEI P5 edition (CC BY-SA 2.5 TW)"

    DILA_ZIP_FILENAME = "dingfubao.dila.tei.p5.xml.zip"
    DICT_LANG = "zh"

    def parse_entry(self, entry_el, index: int) -> dict | None:
        """
        DFB format:
        <entry>
          <form>词头</form>
          <sense>
            <usg type="dom">类别</usg>
            <def>释义</def>
          </sense>
        </entry>
        May have multiple <sense> blocks.
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

        # Collect definitions from all <sense>/<def> elements
        definitions = []
        categories = []

        for sense_el in entry_el.findall(f"{{{TEI_NS}}}sense") or entry_el.findall("sense"):
            # Category from <usg>
            usg_el = sense_el.find(f"{{{TEI_NS}}}usg")
            if usg_el is None:
                usg_el = sense_el.find("usg")
            if usg_el is not None:
                cat = self._strip_tags(usg_el).strip()
                if cat:
                    categories.append(cat)

            # Definition from <def>
            def_el = sense_el.find(f"{{{TEI_NS}}}def")
            if def_el is None:
                def_el = sense_el.find("def")
            if def_el is not None:
                defn = self._strip_tags(def_el).strip()
                if defn:
                    definitions.append(defn)

        # If no <def>, try the whole <sense> text
        if not definitions:
            for sense_el in entry_el.findall(f"{{{TEI_NS}}}sense") or entry_el.findall("sense"):
                text = self._strip_tags(sense_el).strip()
                if text:
                    definitions.append(text)

        if not definitions:
            return None

        definition = "\n\n".join(definitions)

        entry_data = None
        if categories:
            entry_data = {"category": categories[0] if len(categories) == 1 else categories}

        return {
            "headword": headword,
            "reading": None,
            "definition": definition,
            "external_id": f"dfb-{index}",
            "entry_data": entry_data,
        }


async def main():
    parser = argparse.ArgumentParser(description="Import 丁福保佛学大辞典")
    parser.add_argument("--limit", type=int, default=0, help="Limit entries")
    args = parser.parse_args()

    importer = DingFuBaoImporter(limit=args.limit)
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
