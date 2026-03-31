"""
Import 释智谕《南山律学辞典》from DILA TEI P5 XML.

Source: https://glossaries.dila.edu.tw/glossaries/NSL (CC BY-SA / CC0)
Contains Buddhist Vinaya (monastic discipline) terminology.

Usage:
    python scripts/import_nanshanlu.py
    python scripts/import_nanshanlu.py --limit 100
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.import_dila_dict import TEI_NS, DilaBaseImporter


class NanshanluImporter(DilaBaseImporter):
    SOURCE_CODE = "dila-nanshanlu"
    SOURCE_NAME_ZH = "南山律学辞典"
    SOURCE_NAME_EN = "Nanshan Vinaya Dictionary"
    SOURCE_BASE_URL = "https://glossaries.dila.edu.tw/glossaries/NSL"
    SOURCE_DESCRIPTION = "释智谕编《南山律学辞典》, DILA TEI P5 edition, 佛教戒律学专业术语辞典"

    DILA_ZIP_FILENAME = "nanshanlu.dila.tei.p5.xml.zip"
    DICT_LANG = "zh"

    def parse_entry(self, entry_el, index: int) -> dict | None:
        """
        NSL format (same structure as DFB):
        <entry>
          <form>词头</form>
          <sense>
            <def>释义</def>
          </sense>
        </entry>
        """
        form_el = entry_el.find(f"{{{TEI_NS}}}form")
        if form_el is None:
            form_el = entry_el.find("form")
        if form_el is None:
            return None

        headword = self._strip_tags(form_el).strip()
        if not headword:
            return None

        definitions = []
        for sense_el in entry_el.findall(f"{{{TEI_NS}}}sense") or entry_el.findall("sense"):
            def_el = sense_el.find(f"{{{TEI_NS}}}def")
            if def_el is None:
                def_el = sense_el.find("def")
            if def_el is not None:
                defn = self._strip_tags(def_el).strip()
                if defn:
                    definitions.append(defn)

        if not definitions:
            for sense_el in entry_el.findall(f"{{{TEI_NS}}}sense") or entry_el.findall("sense"):
                text = self._strip_tags(sense_el).strip()
                if text:
                    definitions.append(text)

        if not definitions:
            return None

        return {
            "headword": headword,
            "reading": None,
            "definition": "\n\n".join(definitions),
            "external_id": f"nsl-{index}",
            "entry_data": None,
        }


async def main():
    parser = argparse.ArgumentParser(description="Import 南山律学辞典")
    parser.add_argument("--limit", type=int, default=0, help="Limit entries")
    args = parser.parse_args()

    importer = NanshanluImporter(limit=args.limit)
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
