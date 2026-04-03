"""
Import 7 Buddhist dictionaries from buddhaspace.org/dict/.

Source: https://buddhaspace.org/dict/ (台大獅子吼佛學專站)
Dictionaries:
  1. 一切經音義 慧琳音義 (ecg)   ~31K entries
  2. 翻梵語 (ffy)              ~4.7K entries
  3. 法相辭典 朱芾煌 (fxcd)     ~14.7K entries
  4. 佛學常見詞彙 陳義孝 (cxy)   ~5.9K entries
  5. 阿含辭典 莊春江 (ccj)      ~4.6K entries
  6. 續一切經音義 希麟 (secg)    ~1.5K entries
  7. 新集藏經音義隨函錄 (gjg)    ~72K entries

Note: 佛光大辭典 and 中華佛教百科全書 are NOT included here because
they are already imported from higher-quality sources (foguang, zhonghua-baike).

Each dictionary has an index page at /dict/{code}/data/ listing all entries as links,
and individual entry pages at /dict/{code}/data/{double-url-encoded-headword}.html.

Usage:
    python scripts/import_buddhaspace.py
    python scripts/import_buddhaspace.py --dict fk         # import only 佛光大辭典
    python scripts/import_buddhaspace.py --dict fk --limit 100
    python scripts/import_buddhaspace.py --list            # list available dictionaries
"""

import argparse
import asyncio
import json
import os
import re
import sys
from urllib.parse import unquote, urljoin

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.base_importer import BaseImporter
from sqlalchemy import text

BASE_URL = "https://buddhaspace.org/dict/"

# Dictionary configs: (path_code, source_code, name_zh, name_en, description)
DICTIONARIES = [
    # Note: 佛光大辭典(fk) and 中華佛教百科全書(ch) removed — already in DB
    # from higher-quality sources (foguang: 32K, zhonghua-baike: 6.4K).
    {
        "path": "ecg",
        "source_code": "bs-yiqiejing-yinyi",
        "name_zh": "一切經音義（慧琳音義）",
        "name_en": "Yiqiejing Yinyi (Huilin)",
        "description": "一切經音義，翻經沙門慧琳撰。via buddhaspace.org",
    },
    {
        "path": "ffy",
        "source_code": "bs-fanfanyu",
        "name_zh": "翻梵語",
        "name_en": "Fanfanyu (Sanskrit-Chinese Translation Dictionary)",
        "description": "翻梵語，梁·寶唱等集。via buddhaspace.org",
    },
    {
        "path": "fxcd",
        "source_code": "bs-faxiang",
        "name_zh": "法相辭典（朱芾煌）",
        "name_en": "Faxiang Dictionary (Zhu Feihuang)",
        "description": "法相辭典，朱芾煌編。via buddhaspace.org",
    },
    {
        "path": "cxy",
        "source_code": "bs-changjianci",
        "name_zh": "佛學常見詞彙（陳義孝）",
        "name_en": "Common Buddhist Terms (Chen Yixiao)",
        "description": "佛學常見詞彙，陳義孝居士編著。via buddhaspace.org",
    },
    {
        "path": "ccj",
        "source_code": "bs-agama",
        "name_zh": "阿含辭典（莊春江）",
        "name_en": "Agama Dictionary (Zhuang Chunjiang)",
        "description": "阿含辭典，莊春江居士編著。via buddhaspace.org",
    },
    {
        "path": "secg",
        "source_code": "bs-xu-yinyi",
        "name_zh": "續一切經音義（希麟）",
        "name_en": "Supplement to Yiqiejing Yinyi (Xilin)",
        "description": "續一切經音義，遼·希麟集。via buddhaspace.org",
    },
    {
        "path": "gjg",
        "source_code": "bs-suihan-lu",
        "name_zh": "新集藏經音義隨函錄（可洪）",
        "name_en": "Xinji Zangjing Yinyi Suihan Lu (Kehong)",
        "description": "新集藏經音義隨函錄，後唐·可洪撰。via buddhaspace.org",
    },
]


def _decode_double_encoded(href: str) -> str:
    """Decode a double-URL-encoded href to get the actual filename.

    buddhaspace.org uses double encoding: %25E4%25B8%2580 -> %E4%B8%80 -> 一
    """
    # First decode: %25 -> %
    once = unquote(href)
    # Second decode: %E4%B8%80 -> 一
    twice = unquote(once)
    return twice


def _strip_html(html: str) -> str:
    """Strip HTML tags and normalize whitespace, preserving paragraph breaks."""
    # Replace <br> / <br/> / <p> with newlines
    text_out = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text_out = re.sub(r"</?p[^>]*>", "\n", text_out, flags=re.IGNORECASE)
    # Remove all other HTML tags
    text_out = re.sub(r"<[^>]+>", "", text_out)
    # Decode HTML entities
    text_out = text_out.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text_out = text_out.replace("&nbsp;", " ").replace("&quot;", '"')
    # Normalize whitespace per line, collapse blank lines
    lines = [line.strip() for line in text_out.split("\n")]
    text_out = "\n".join(line for line in lines if line)
    return text_out.strip()


def _parse_index_page(html: str) -> list[tuple[str, str]]:
    """Parse the index page to extract (headword, relative_href) pairs.

    The index page contains links like:
        <a href="%25E4%25B8%2580.html">一</a>
    or in markdown conversion:
        [一](%25E4%25B8%2580.html)
    We use regex to find all <a href="...">...</a> patterns in the raw HTML.
    """
    entries = []
    # Match href links pointing to .html files
    # Pattern handles both encoded and plain hrefs
    for match in re.finditer(r'href="([^"]+\.html)"[^>]*>([^<]+)</a>', html, re.IGNORECASE):
        href = match.group(1)
        link_text = match.group(2).strip().strip("\ufeff")  # strip BOM
        if link_text:
            entries.append((link_text, href))

    if not entries:
        # Fallback: try matching markdown-style links from converted content
        for match in re.finditer(r'\[([^\]]+)\]\(([^)]+\.html)\)', html):
            link_text = match.group(1).strip()
            href = match.group(2)
            if link_text:
                entries.append((link_text, href))

    return entries


def _extract_definition(html: str, headword: str) -> str:
    """Extract definition text from an entry page HTML.

    Entry pages are full HTML pages. The actual definition is between
    <!--DESCRIPTIONSTART--> and <!--DESCRIPTIONEND--> comments when present,
    otherwise we fall back to stripping boilerplate from the full text.
    """
    # Try to extract between DESCRIPTION markers first
    desc_match = re.search(
        r"<!--DESCRIPTIONSTART-->(.*?)<!--DESCRIPTIONEND-->", html, re.DOTALL
    )
    if desc_match:
        definition_html = desc_match.group(1)
    else:
        # Fallback: extract from <BODY> content
        body_match = re.search(r"<BODY[^>]*>(.*?)</BODY>", html, re.DOTALL | re.IGNORECASE)
        definition_html = body_match.group(1) if body_match else html

    text_content = _strip_html(definition_html)

    # Remove common boilerplate lines
    lines = text_content.split("\n")
    cleaned = []
    for line in lines:
        if "台大獅子吼佛學專站" in line:
            continue
        if "buddhaspace.org" in line:
            continue
        if "卍歡迎光臨" in line:
            continue
        cleaned.append(line)

    text_content = "\n".join(cleaned).strip()

    # Remove the headword if it appears as the first line (title)
    first_line_end = text_content.find("\n")
    if first_line_end > 0:
        first_line = text_content[:first_line_end].strip()
        if first_line == headword:
            text_content = text_content[first_line_end:].strip()
    elif text_content.strip() == headword:
        return ""

    # Remove source attribution lines at the start
    attribution_pattern = re.compile(
        r"^(?:佛光大辭典|中華佛教百科全書|一切經音義|翻梵語|法相辭典|佛學常見詞彙|阿含辭典)"
        r"\s*[\(（].*?[\)）]\s*$",
        re.MULTILINE,
    )
    text_content = attribution_pattern.sub("", text_content).strip()

    return text_content


class BuddhaspaceImporter(BaseImporter):
    SOURCE_CODE = "buddhaspace"  # placeholder, overridden per dict
    SOURCE_NAME_ZH = ""
    SOURCE_NAME_EN = ""
    SOURCE_BASE_URL = "https://buddhaspace.org/dict/"
    SOURCE_DESCRIPTION = ""
    RATE_LIMIT_DELAY = 0.15  # 150ms between requests (avoid rate limiting)
    CONCURRENCY = 5  # parallel fetches

    def __init__(self, dict_configs: list[dict], limit: int = 0, concurrency: int = 0):
        super().__init__()
        self.dict_configs = dict_configs
        self.limit = limit
        if concurrency > 0:
            self.CONCURRENCY = concurrency
        self._semaphore = asyncio.Semaphore(self.CONCURRENCY)
        # Override SOURCE_CODE for checkpoint naming
        if len(dict_configs) == 1:
            self.SOURCE_CODE = dict_configs[0]["source_code"]
            self.SOURCE_NAME_ZH = dict_configs[0]["name_zh"]
            self.SOURCE_NAME_EN = dict_configs[0]["name_en"]
        else:
            self.SOURCE_CODE = "buddhaspace-all"
            self.SOURCE_NAME_ZH = "Buddhaspace 九部辞典"
            self.SOURCE_NAME_EN = "Buddhaspace 9 Dictionaries"

    async def _fetch_index(self, dict_path: str) -> list[tuple[str, str]]:
        """Fetch the index page for a dictionary and parse entry links."""
        index_url = f"{BASE_URL}{dict_path}/data/"
        print(f"  Fetching index: {index_url}")

        resp = await self.rate_limited_get(index_url)
        raw_html = resp.text
        entries = _parse_index_page(raw_html)
        print(f"  Found {len(entries)} entries in index.")
        return entries

    async def _fetch_entry(self, dict_path: str, href: str) -> str | None:
        """Fetch a single dictionary entry page with concurrency control."""
        entry_url = urljoin(f"{BASE_URL}{dict_path}/data/", href)
        async with self._semaphore:
            try:
                resp = await self.rate_limited_get(entry_url)
                return resp.text
            except Exception as e:
                print(f"    Error fetching {entry_url}: {e}")
                self.stats.errors += 1
                return None

    async def _fetch_batch(self, dict_path: str, batch: list[tuple[str, str]]) -> list[tuple[str, str, str | None]]:
        """Fetch a batch of entries concurrently. Returns [(headword, href, html), ...]."""
        tasks = []
        for headword, href in batch:
            tasks.append(self._fetch_entry(dict_path, href))
        results = await asyncio.gather(*tasks)
        return [(hw, href, html) for (hw, href), html in zip(batch, results)]

    async def _import_one_dict(self, config: dict):
        """Import a single dictionary with concurrent fetching."""
        path = config["path"]
        source_code = config["source_code"]
        name_zh = config["name_zh"]
        name_en = config["name_en"]
        description = config["description"]

        print(f"\n{'─' * 50}")
        print(f"  Importing: {name_zh} ({source_code})")
        print(f"{'─' * 50}")

        # Load checkpoint for this specific dictionary
        checkpoint_key = f"done_{source_code}"
        checkpoint = self.load_checkpoint()
        done_ids: set[str] = set(checkpoint.get(checkpoint_key, []))

        # Fetch index
        entries = await self._fetch_index(path)
        if not entries:
            print(f"  WARNING: No entries found for {name_zh}, skipping.")
            return

        # Filter out already-done entries
        todo = []
        skipped = 0
        for headword, href in entries:
            external_id = f"{source_code}-{headword}"
            if external_id in done_ids:
                skipped += 1
            else:
                todo.append((headword, href))

        if not todo:
            print(f"  {name_zh}: all {skipped} entries already done, skipping.")
            return

        if self.limit > 0:
            todo = todo[:self.limit]

        print(f"  {len(todo)} entries to fetch ({skipped} already done), concurrency={self.CONCURRENCY}")

        async with self.session_factory() as session:
            self._source = None
            self.SOURCE_CODE = source_code
            self.SOURCE_NAME_ZH = name_zh
            self.SOURCE_NAME_EN = name_en
            self.SOURCE_DESCRIPTION = description
            source = await self.ensure_source(session)
            source_id = source.id

            imported = 0
            batch_size = self.CONCURRENCY * 5  # fetch 50 at a time

            for i in range(0, len(todo), batch_size):
                batch = todo[i:i + batch_size]
                results = await self._fetch_batch(path, batch)

                for headword, href, entry_html in results:
                    if not entry_html:
                        continue

                    definition = _extract_definition(entry_html, headword)
                    external_id = f"{source_code}-{headword}"

                    if not definition:
                        skipped += 1
                        done_ids.add(external_id)
                        continue

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
                            "reading": None,
                            "definition": definition,
                            "source_id": source_id,
                            "lang": "zh",
                            "external_id": external_id[:200],
                            "entry_data": json.dumps(
                                {"source_url": f"{BASE_URL}{path}/data/{href}"},
                                ensure_ascii=False,
                            ),
                        },
                    )
                    imported += 1
                    done_ids.add(external_id)

                await session.commit()
                checkpoint[checkpoint_key] = list(done_ids)
                self.save_checkpoint(checkpoint)

                if imported % 500 < batch_size:
                    print(f"    ... {imported} entries imported ({skipped} skipped)")

            await session.commit()

        checkpoint[checkpoint_key] = list(done_ids)
        self.save_checkpoint(checkpoint)

        self.stats.texts_created += imported
        self.stats.skipped += skipped
        print(f"  {name_zh}: imported {imported}, skipped {skipped}.")

    async def run_import(self):
        for config in self.dict_configs:
            await self._import_one_dict(config)

        print(f"\n  Total: {self.stats.texts_created} imported, {self.stats.skipped} skipped, "
              f"{self.stats.errors} errors.")


async def main():
    parser = argparse.ArgumentParser(description="Import Buddhist dictionaries from buddhaspace.org")
    parser.add_argument("--dict", type=str, default=None,
                        help="Import only this dictionary (path code: fk, ch, ecg, ffy, fxcd, cxy, ccj)")
    parser.add_argument("--limit", type=int, default=0, help="Limit entries per dictionary (0 = no limit)")
    parser.add_argument("--concurrency", type=int, default=0, help="Concurrent fetches (default: 10)")
    parser.add_argument("--list", action="store_true", help="List available dictionaries and exit")
    args = parser.parse_args()

    if args.list:
        print("Available dictionaries from buddhaspace.org:")
        print(f"  {'Code':<8} {'Source Code':<22} {'Name'}")
        print(f"  {'─' * 8} {'─' * 22} {'─' * 30}")
        for d in DICTIONARIES:
            print(f"  {d['path']:<8} {d['source_code']:<22} {d['name_zh']}")
        return

    if args.dict:
        configs = [d for d in DICTIONARIES if d["path"] == args.dict]
        if not configs:
            valid = ", ".join(d["path"] for d in DICTIONARIES)
            print(f"Error: Unknown dictionary '{args.dict}'. Valid codes: {valid}")
            sys.exit(1)
    else:
        configs = DICTIONARIES

    importer = BuddhaspaceImporter(dict_configs=configs, limit=args.limit, concurrency=args.concurrency)
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
