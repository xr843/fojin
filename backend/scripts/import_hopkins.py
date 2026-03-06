"""
Import Jeffrey Hopkins Tibetan-Sanskrit-English Dictionary from DILA TEI P5 XML.

Source: https://glossaries.dila.edu.tw/glossaries/JHK
Contains ~18,400 Tibetan→Sanskrit/English entries.

Usage:
    python scripts/import_hopkins.py
    python scripts/import_hopkins.py --limit 100
"""

import asyncio
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.import_dila_dict import DilaBaseImporter, TEI_NS


class HopkinsImporter(DilaBaseImporter):
    SOURCE_CODE = "dila-hopkins"
    SOURCE_NAME_ZH = "Hopkins 藏梵英辞典"
    SOURCE_NAME_EN = "Jeffrey Hopkins Tibetan-Sanskrit-English Dictionary"
    SOURCE_BASE_URL = "https://glossaries.dila.edu.tw/glossaries/JHK"
    SOURCE_DESCRIPTION = "Jeffrey Hopkins Tibetan-Sanskrit-English Dictionary, DILA TEI P5 edition"

    DILA_ZIP_FILENAME = "hopkins.dila.tei.p5.xml.zip"
    DICT_LANG = "bo"

    def parse_entry(self, entry_el, index: int) -> dict | None:
        """
        Hopkins format:
        <entry>
          <form>tibetan wylie</form>
          <sense>
            <cit type="translation" xml:lang="eng"><bibl>Hopkins</bibl><quote>English</quote></cit>
            <cit type="definition" xml:lang="bod"><lbl>mtshan nyid</lbl><quote>Tibetan def</quote></cit>
            <cit type="definition" xml:lang="eng"><lbl>Def.:</lbl><quote>English def</quote></cit>
            <note>Comment: ...</note>
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

        sense_el = entry_el.find(f"{{{TEI_NS}}}sense")
        if sense_el is None:
            sense_el = entry_el.find("sense")
        if sense_el is None:
            return None

        # Extract translations and definitions from <cit> elements
        translations = []
        sanskrit_terms = []
        definitions_bo = []
        definitions_en = []
        entry_data = {}

        cit_els = sense_el.findall(f"{{{TEI_NS}}}cit")
        if not cit_els:
            cit_els = sense_el.findall("cit")
        for cit_el in cit_els:
            cit_type = cit_el.get("type", "")
            cit_lang = cit_el.get("{http://www.w3.org/XML/1998/namespace}lang", "")

            quote_el = cit_el.find(f"{{{TEI_NS}}}quote")
            if quote_el is None:
                quote_el = cit_el.find("quote")
            if quote_el is None:
                continue
            quote_text = self._strip_tags(quote_el).strip()
            if not quote_text:
                continue

            if cit_type == "translation":
                if "eng" in cit_lang:
                    translations.append(quote_text)
                elif "san" in cit_lang:
                    sanskrit_terms.append(quote_text)
            elif cit_type == "definition":
                if "bod" in cit_lang:
                    definitions_bo.append(quote_text)
                elif "eng" in cit_lang:
                    definitions_en.append(quote_text)

        # Extract notes
        notes = []
        note_els = sense_el.findall(f"{{{TEI_NS}}}note")
        if not note_els:
            note_els = sense_el.findall("note")
        for note_el in note_els:
            note_text = self._strip_tags(note_el).strip()
            if note_text:
                notes.append(note_text)

        # Build definition: translation first, then English definition, then notes
        parts = []
        if translations:
            parts.append("; ".join(translations))
        if definitions_en:
            parts.append("Def.: " + "; ".join(definitions_en))
        if notes:
            parts.append("\n".join(notes))

        definition = "\n\n".join(parts)
        if not definition:
            return None

        if definitions_bo:
            entry_data["definition_bo"] = definitions_bo[0] if len(definitions_bo) == 1 else definitions_bo
        if sanskrit_terms:
            entry_data["sanskrit"] = sanskrit_terms[0] if len(sanskrit_terms) == 1 else sanskrit_terms

        return {
            "headword": headword,
            "reading": None,
            "definition": definition,
            "external_id": f"jhk-{index}",
            "entry_data": entry_data if entry_data else None,
        }


async def main():
    parser = argparse.ArgumentParser(description="Import Hopkins Tibetan-Sanskrit-English dictionary")
    parser.add_argument("--limit", type=int, default=0, help="Limit entries")
    args = parser.parse_args()

    importer = HopkinsImporter(limit=args.limit)
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
