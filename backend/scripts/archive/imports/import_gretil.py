"""
Import GRETIL Sanskrit Buddhist texts.

GRETIL (Göttingen Register of Electronic Texts in Indian Languages) hosts
a large collection of Sanskrit Buddhist texts as downloadable plain text files.

Usage:
    python scripts/import_gretil.py
    python scripts/import_gretil.py --limit 10
    python scripts/import_gretil.py --local-dir data/gretil
"""

import argparse
import asyncio
import os
import re
import sys
from html import unescape
from urllib.parse import urljoin, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elasticsearch.helpers import async_bulk
from scripts.base_importer import BaseImporter
from sqlalchemy import text

from app.core.elasticsearch import CONTENT_INDEX_NAME, INDEX_NAME
from app.core.gretil_parser import parse_gretil_file

# GRETIL Buddhism section index URL
GRETIL_SITE_BASE = "https://gretil.sub.uni-goettingen.de"
GRETIL_BASE = f"{GRETIL_SITE_BASE}/gretil"
GRETIL_BUDDHISM_INDEX = f"{GRETIL_SITE_BASE}/gretil.html"


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value).strip()


def _buddhist_sections(html: str) -> list[str]:
    """Return sections headed by a Buddhist heading in the single-page index."""
    headings = list(re.finditer(r"<h([1-6])\b[^>]*>(.*?)</h\1>", html, re.IGNORECASE | re.DOTALL))
    sections = []

    for index, heading in enumerate(headings):
        title = unescape(_strip_tags(heading.group(2)))
        if title.lower() != "buddhist":
            continue

        level = int(heading.group(1))
        end = len(html)
        for next_heading in headings[index + 1:]:
            if int(next_heading.group(1)) <= level:
                end = next_heading.start()
                break

        sections.append(html[heading.end():end])

    return sections


def _is_gretil_text_href(href: str) -> bool:
    parsed_path = urlparse(href).path.lower()
    if "/corpustei/" not in parsed_path:
        return False
    return parsed_path.endswith(".xml") or (
        "/transformations/plaintext/" in parsed_path and parsed_path.endswith(".txt")
    )


def _gretil_text_key(url: str) -> str:
    return os.path.splitext(os.path.basename(urlparse(url).path))[0]


def _gretil_href_priority(url: str) -> int:
    parsed_path = urlparse(url).path.lower()
    if "/transformations/plaintext/" in parsed_path and parsed_path.endswith(".txt"):
        return 0
    return 1


def _discover_links_from_gretil_html(html: str) -> list[dict]:
    texts_by_key: dict[str, tuple[int, dict]] = {}

    for section in _buddhist_sections(html):
        for match in re.finditer(r"""href\s*=\s*["']([^"']+)["']""", section, re.IGNORECASE):
            href = unescape(match.group(1))
            if not _is_gretil_text_href(href):
                continue

            url = urljoin(GRETIL_BUDDHISM_INDEX, href)
            key = _gretil_text_key(url)
            priority = _gretil_href_priority(url)
            existing = texts_by_key.get(key)
            if existing is not None and existing[0] <= priority:
                continue

            texts_by_key[key] = (
                priority,
                {
                    "url": url,
                    "filename": os.path.basename(urlparse(url).path),
                    "category": "Buddhism",
                },
            )

    return [item for _, item in texts_by_key.values()]


class GRETILImporter(BaseImporter):
    SOURCE_CODE = "gretil"
    SOURCE_NAME_ZH = "GRETIL 梵文文献库"
    SOURCE_NAME_EN = "Göttingen Register of Electronic Texts in Indian Languages"
    SOURCE_BASE_URL = "https://gretil.sub.uni-goettingen.de"
    SOURCE_DESCRIPTION = "哥廷根大学印度语言电子文本登记册，收录大量梵文佛教文献"
    RATE_LIMIT_DELAY = 2.0  # Be polite to GRETIL

    def __init__(self, limit: int = 0, local_dir: str | None = None):
        super().__init__()
        self.limit = limit
        self.local_dir = local_dir

    async def discover_texts(self) -> list[dict]:
        """Discover available Buddhist Sanskrit texts from GRETIL.

        Returns list of {url, filename, category}.
        """
        if self.local_dir and os.path.isdir(self.local_dir):
            # Use local files
            texts = []
            for f in sorted(os.listdir(self.local_dir)):
                if f.endswith((".txt", ".htm", ".html", ".xml")):
                    texts.append({
                        "url": None,
                        "filename": f,
                        "local_path": os.path.join(self.local_dir, f),
                        "category": "Buddhism",
                    })
            print(f"  Found {len(texts)} local files in {self.local_dir}")
            return texts

        # Fetch index page to discover files
        print("  Fetching GRETIL Buddhism index...")
        try:
            resp = await self.rate_limited_get(GRETIL_BUDDHISM_INDEX)
            html = resp.text
        except Exception as e:
            print(f"  Could not fetch index: {e}")
            print("  Trying alternative structure...")
            return await self._discover_from_directory()

        texts = _discover_links_from_gretil_html(html)

        print(f"  Discovered {len(texts)} Buddhist Sanskrit texts from index.")
        return texts

    async def _discover_from_directory(self) -> list[dict]:
        """Alternative discovery using known GRETIL directory structure."""
        # Well-known GRETIL Buddhist text categories
        known_dirs = [
            "1_sanskr/4_rellit/buddh",
        ]

        texts = []
        for dir_path in known_dirs:
            try:
                resp = await self.rate_limited_get(f"{GRETIL_BASE}/{dir_path}/")
                html = resp.text

                for match in re.finditer(r'href="([^"]+\.(?:txt|htm))"', html):
                    filename = match.group(1)
                    url = f"{GRETIL_BASE}/{dir_path}/{filename}"
                    texts.append({
                        "url": url,
                        "filename": filename,
                        "category": "Buddhism",
                    })
            except Exception as e:
                print(f"  Could not list {dir_path}: {e}")

        print(f"  Discovered {len(texts)} texts from directory listing.")
        return texts

    async def run_import(self):
        texts = await self.discover_texts()

        if self.limit > 0:
            texts = texts[:self.limit]

        if not texts:
            print("  No texts found to import.")
            return

        print(f"\n  Importing {len(texts)} GRETIL texts...")

        async with self.session_factory() as session:
            source = await self.ensure_source(session)
            es_text_actions = []
            es_content_actions = []

            for i, info in enumerate(texts):
                filename = info["filename"]
                name_base = os.path.splitext(filename)[0]
                cbeta_id = f"GRETIL-{name_base}"

                try:
                    # Get content
                    if info.get("local_path"):
                        with open(info["local_path"], encoding="utf-8", errors="replace") as f:
                            raw = f.read()
                    else:
                        resp = await self.rate_limited_get(info["url"])
                        raw = resp.text

                    parsed = parse_gretil_file(raw, filename)

                    if not parsed["content"].strip():
                        self.stats.skipped += 1
                        continue

                    title = parsed["title"] or name_base
                    title_sa = title

                    # Upsert BuddhistText
                    result = await session.execute(
                        text("""
                            INSERT INTO buddhist_texts
                                (cbeta_id, title_zh, title_sa, source_id, lang, has_content,
                                 content_char_count)
                            VALUES (:cbeta_id, :title_zh, :title_sa, :source_id, 'sa', true,
                                    :char_count)
                            ON CONFLICT (cbeta_id) DO UPDATE SET
                                title_sa = COALESCE(EXCLUDED.title_sa, buddhist_texts.title_sa),
                                has_content = true,
                                content_char_count = EXCLUDED.content_char_count
                            RETURNING id
                        """),
                        {
                            "cbeta_id": cbeta_id,
                            "title_zh": title_sa,  # Use Sanskrit title as display
                            "title_sa": title_sa,
                            "source_id": source.id,
                            "char_count": parsed["char_count"],
                        },
                    )
                    text_id = result.scalar_one()
                    self.stats.texts_created += 1

                    # TextIdentifier
                    await session.execute(
                        text("""
                            INSERT INTO text_identifiers (text_id, source_id, source_uid, source_url)
                            VALUES (:text_id, :source_id, :uid, :url)
                            ON CONFLICT ON CONSTRAINT uq_text_identifier_source_uid DO NOTHING
                        """),
                        {
                            "text_id": text_id,
                            "source_id": source.id,
                            "uid": name_base,
                            "url": info.get("url") or f"{GRETIL_BASE}/1_sanskr/4_rellit/buddh/{filename}",
                        },
                    )
                    self.stats.identifiers_created += 1

                    # TextContent
                    await session.execute(
                        text("""
                            INSERT INTO text_contents (text_id, juan_num, content, char_count, lang)
                            VALUES (:text_id, 1, :content, :char_count, 'sa')
                            ON CONFLICT ON CONSTRAINT uq_text_content_text_juan_lang DO UPDATE SET
                                content = EXCLUDED.content,
                                char_count = EXCLUDED.char_count
                        """),
                        {
                            "text_id": text_id,
                            "content": parsed["content"],
                            "char_count": parsed["char_count"],
                        },
                    )
                    self.stats.contents_created += 1

                    # ES actions
                    es_text_actions.append({
                        "_index": INDEX_NAME,
                        "_id": str(text_id),
                        "_source": {
                            "id": text_id,
                            "cbeta_id": cbeta_id,
                            "title_zh": title_sa,
                            "title_sa": title_sa,
                            "lang": "sa",
                            "source_code": "gretil",
                        },
                    })
                    es_content_actions.append({
                        "_index": CONTENT_INDEX_NAME,
                        "_id": f"{text_id}_1_sa",
                        "_source": {
                            "text_id": text_id,
                            "cbeta_id": cbeta_id,
                            "title_zh": title_sa,
                            "juan_num": 1,
                            "content": parsed["content"],
                            "char_count": parsed["char_count"],
                            "lang": "sa",
                            "source_code": "gretil",
                        },
                    })

                except Exception as e:
                    self.stats.errors += 1
                    print(f"  Error importing {filename}: {e}")

                if (i + 1) % 20 == 0:
                    await session.flush()
                    print(f"  Progress: {i + 1}/{len(texts)}, {self.stats.summary()}")

            await session.commit()

        # Bulk ES index
        if es_text_actions:

            async def gen_texts():
                for a in es_text_actions:
                    yield a

            async def gen_contents():
                for a in es_content_actions:
                    yield a

            s1, _ = await async_bulk(self.es, gen_texts(), raise_on_error=False)
            s2, _ = await async_bulk(self.es, gen_contents(), raise_on_error=False)
            print(f"  ES: indexed {s1} texts, {s2} contents")


async def main():
    parser = argparse.ArgumentParser(description="Import GRETIL Sanskrit Buddhist texts")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of texts")
    parser.add_argument("--local-dir", type=str, help="Use local directory instead of downloading")
    args = parser.parse_args()

    importer = GRETILImporter(limit=args.limit, local_dir=args.local_dir)
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
