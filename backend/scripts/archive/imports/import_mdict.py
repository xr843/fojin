"""
Generic MDict (.mdx) dictionary importer.

Reads a .mdx file using mdict_utils, strips HTML from definitions,
and inserts into dictionary_entries with ON CONFLICT DO UPDATE.

Usage:
    python scripts/import_mdict.py --file /path/to/dict.mdx --code foguang --name-zh "佛光大辭典" --lang lzh
    python scripts/import_mdict.py --file /path/to/dict.mdx --code foguang --name-zh "佛光大辭典" --lang lzh --limit 100
    python scripts/import_mdict.py --file /path/to/dict.mdx --code foguang --name-zh "佛光大辭典" --lang lzh --dry-run
"""

import argparse
import asyncio
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mdict_utils.reader import MDX
from scripts.base_importer import BaseImporter
from sqlalchemy import text


def strip_html(html_str: str) -> str:
    """Strip HTML tags, decode entities, normalize whitespace."""
    if not html_str:
        return ""
    # Remove <style>...</style> and <script>...</script> blocks
    s = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", html_str, flags=re.DOTALL | re.IGNORECASE)
    # Replace <br>, <p>, <div>, <li> with newlines for readability
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"</(p|div|li|tr|h[1-6])>", "\n", s, flags=re.IGNORECASE)
    # Remove all remaining tags
    s = re.sub(r"<[^>]+>", "", s)
    # Decode common HTML entities
    s = s.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">")
    s = s.replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
    # Normalize whitespace: collapse multiple spaces on same line, strip trailing
    lines = [line.strip() for line in s.split("\n")]
    s = "\n".join(line for line in lines if line)
    return s.strip()


def extract_reading(headword: str, definition: str) -> str | None:
    """Try to extract a reading/pinyin from the definition if present."""
    # Common pattern: first line is pinyin in parentheses or brackets
    m = re.match(r"^[（\(]\s*([a-zA-Zāáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ\s]+)\s*[）\)]", definition)
    if m:
        return m.group(1).strip()
    return None


class MdictImporter(BaseImporter):
    """Import a generic MDict (.mdx) dictionary file."""

    def __init__(self, mdx_path: str, code: str, name_zh: str, name_en: str, lang: str, limit: int, dry_run: bool):
        self.SOURCE_CODE = code
        self.SOURCE_NAME_ZH = name_zh
        self.SOURCE_NAME_EN = name_en or name_zh
        self.DICT_LANG = lang

        super().__init__()
        self.mdx_path = mdx_path
        self.limit = limit
        self.dry_run = dry_run

    async def run_import(self):
        print(f"  Reading MDict file: {self.mdx_path}")
        mdx = MDX(self.mdx_path)
        total = len(mdx)
        print(f"  Total entries in MDX: {total}")

        items = list(mdx.items())
        if self.limit > 0:
            items = items[: self.limit]
            print(f"  Limiting to {self.limit} entries.")

        # Preview first 3 entries
        print("\n  === Preview (first 3 entries) ===")
        for key_bytes, val_bytes in items[:3]:
            key = key_bytes.decode("utf-8", errors="replace") if isinstance(key_bytes, bytes) else str(key_bytes)
            val = val_bytes.decode("utf-8", errors="replace") if isinstance(val_bytes, bytes) else str(val_bytes)
            clean = strip_html(val)
            print(f"  [{key}]")
            print(f"    raw ({len(val)} chars): {val[:200]}...")
            print(f"    clean: {clean[:200]}...")
            print()

        if self.dry_run:
            print(f"  DRY RUN: would import {len(items)} entries. Exiting.")
            self.stats.skipped = len(items)
            return

        async with self.session_factory() as session:
            source = await self.ensure_source(session)

            imported = 0
            skipped = 0

            for _i, (key_bytes, val_bytes) in enumerate(items):
                key = key_bytes.decode("utf-8", errors="replace") if isinstance(key_bytes, bytes) else str(key_bytes)
                val = val_bytes.decode("utf-8", errors="replace") if isinstance(val_bytes, bytes) else str(val_bytes)

                headword = key.strip()
                if not headword:
                    skipped += 1
                    continue

                # Skip MDict internal redirect entries (e.g. @@@LINK=...)
                if val.strip().startswith("@@@LINK="):
                    skipped += 1
                    continue

                definition_html = val
                definition_clean = strip_html(val)

                if not definition_clean:
                    skipped += 1
                    continue

                reading = extract_reading(headword, definition_clean)
                external_id = f"{self.SOURCE_CODE}-{headword}"

                entry_data = {"definition_html": definition_html}
                entry_data_json = json.dumps(entry_data, ensure_ascii=False)

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
                        "reading": (reading or "")[:500] or None,
                        "definition": definition_clean,
                        "source_id": source.id,
                        "lang": self.DICT_LANG,
                        "external_id": external_id[:500],
                        "entry_data": entry_data_json,
                    },
                )
                imported += 1

                if imported % 5000 == 0:
                    await session.commit()
                    print(f"    ... {imported}/{len(items)} entries processed")

            await session.commit()

        self.stats.texts_created = imported
        self.stats.skipped = skipped
        print(f"  Imported {imported} entries, skipped {skipped}.")


def main():
    parser = argparse.ArgumentParser(description="Import MDict (.mdx) dictionary into FoJin")
    parser.add_argument("--file", required=True, help="Path to .mdx file")
    parser.add_argument("--code", required=True, help="Source code (e.g. foguang)")
    parser.add_argument("--name-zh", required=True, help="Chinese name (e.g. 佛光大辭典)")
    parser.add_argument("--name-en", default="", help="English name (optional)")
    parser.add_argument("--lang", default="lzh", help="Language code: lzh (Classical Chinese), zh, en, pi, sa")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of entries (0 = all)")
    parser.add_argument("--dry-run", action="store_true", help="Preview entries without inserting into DB")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"ERROR: File not found: {args.file}")
        sys.exit(1)

    importer = MdictImporter(
        mdx_path=args.file,
        code=args.code,
        name_zh=args.name_zh,
        name_en=args.name_en,
        lang=args.lang,
        limit=args.limit,
        dry_run=args.dry_run,
    )
    asyncio.run(importer.execute())


if __name__ == "__main__":
    main()
