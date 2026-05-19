"""
Import 84000 Tibetan-English Buddhist translations.

84000 (Translating the Words of the Buddha) provides TEI XML translations
from the Tibetan Kangyur and Tengyur.

Usage:
    python scripts/import_84000.py
    python scripts/import_84000.py --limit 10
    python scripts/import_84000.py --local-dir data/84000
"""

import argparse
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.base_importer import BaseImporter
from app.core.tei_84000_parser import parse_84000_tei, extract_toh_number

from sqlalchemy import text
from elasticsearch.helpers import async_bulk

from app.core.elasticsearch import INDEX_NAME, CONTENT_INDEX_NAME


READ_84000_BASE = "https://read.84000.co"


class Import84000(BaseImporter):
    SOURCE_CODE = "84000"
    SOURCE_NAME_ZH = "84000 藏传佛典翻译"
    SOURCE_NAME_EN = "84000: Translating the Words of the Buddha"
    SOURCE_BASE_URL = READ_84000_BASE
    SOURCE_API_URL = f"{READ_84000_BASE}/translation"
    SOURCE_DESCRIPTION = "致力于将藏传佛教大藏经翻译为现代语言的国际非营利项目"
    RATE_LIMIT_DELAY = 3.0  # Be very polite

    def __init__(self, limit: int = 0, local_dir: str | None = None):
        super().__init__()
        self.limit = limit
        self.local_dir = local_dir

    async def discover_texts(self) -> list[dict]:
        """Discover available 84000 translations."""
        if self.local_dir and os.path.isdir(self.local_dir):
            texts = []
            for f in sorted(os.listdir(self.local_dir)):
                if f.endswith(".xml"):
                    toh = extract_toh_number(f)
                    texts.append({
                        "filename": f,
                        "local_path": os.path.join(self.local_dir, f),
                        "toh": toh,
                    })
            print(f"  Found {len(texts)} local 84000 XML files")
            return texts

        # Try fetching the 84000 publication list
        print("  Fetching 84000 translation list...")
        texts = []

        try:
            # 84000 has a reading room with published translations
            resp = await self.rate_limited_get(
                f"{READ_84000_BASE}/section/lobby.html"
            )
            html = resp.text

            # Extract Toh numbers from links
            for match in re.finditer(r'href="[^"]*/(toh\d+(?:-\d+)?)[^"]*\.html"', html):
                toh_id = match.group(1)
                toh_num = re.search(r'\d+', toh_id).group()
                texts.append({
                    "toh": toh_num,
                    "toh_id": toh_id,
                    "url": f"{READ_84000_BASE}/translation/{toh_id}.html",
                    "xml_url": f"{READ_84000_BASE}/translation/{toh_id}.xml",
                })

        except Exception as e:
            print(f"  Could not fetch 84000 listing: {e}")
            # Use known published translations as fallback
            known_tohs = [
                1, 11, 31, 44, 72, 94, 100, 107, 113, 116,
                152, 186, 198, 231, 257, 263, 287, 339, 347, 357,
            ]
            for toh in known_tohs:
                texts.append({
                    "toh": str(toh),
                    "toh_id": f"toh{toh}",
                    "url": f"{READ_84000_BASE}/translation/toh{toh}.html",
                    "xml_url": f"{READ_84000_BASE}/translation/toh{toh}.xml",
                })

        # Deduplicate
        seen = set()
        unique = []
        for t in texts:
            if t["toh"] not in seen:
                seen.add(t["toh"])
                unique.append(t)
        texts = unique

        print(f"  Discovered {len(texts)} translations.")
        return texts

    async def run_import(self):
        texts = await self.discover_texts()

        if self.limit > 0:
            texts = texts[:self.limit]

        if not texts:
            print("  No texts found to import.")
            return

        print(f"\n  Importing {len(texts)} 84000 translations...")

        async with self.session_factory() as session:
            source = await self.ensure_source(session)
            es_text_actions = []
            es_content_actions = []

            for i, info in enumerate(texts):
                toh = info["toh"]
                cbeta_id = f"84K-toh{toh}"

                try:
                    # Get TEI XML
                    if info.get("local_path"):
                        with open(info["local_path"], "r", encoding="utf-8", errors="replace") as f:
                            xml_content = f.read()
                    else:
                        xml_url = info.get("xml_url", f"{READ_84000_BASE}/translation/toh{toh}.xml")
                        try:
                            resp = await self.rate_limited_get(xml_url)
                            xml_content = resp.text
                        except Exception:
                            self.stats.skipped += 1
                            continue

                    parsed = parse_84000_tei(xml_content)

                    title_en = parsed["title_en"] or f"Toh {toh}"
                    title_bo = parsed["title_bo"] or None
                    title_sa = parsed["title_sa"] or None

                    # Upsert BuddhistText
                    result = await session.execute(
                        text("""
                            INSERT INTO buddhist_texts
                                (cbeta_id, title_zh, title_en, title_bo, title_sa,
                                 source_id, lang, has_content)
                            VALUES (:cbeta_id, :title_zh, :title_en, :title_bo, :title_sa,
                                    :source_id, 'bo', :has_content)
                            ON CONFLICT (cbeta_id) DO UPDATE SET
                                title_en = COALESCE(EXCLUDED.title_en, buddhist_texts.title_en),
                                title_bo = COALESCE(EXCLUDED.title_bo, buddhist_texts.title_bo),
                                title_sa = COALESCE(EXCLUDED.title_sa, buddhist_texts.title_sa),
                                has_content = EXCLUDED.has_content
                            RETURNING id
                        """),
                        {
                            "cbeta_id": cbeta_id,
                            "title_zh": title_en,  # Use English as display
                            "title_en": title_en,
                            "title_bo": title_bo,
                            "title_sa": title_sa,
                            "source_id": source.id,
                            "has_content": bool(parsed["translation_en"]),
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
                            "uid": f"toh{toh}",
                            "url": info.get("url", f"{READ_84000_BASE}/translation/toh{toh}.html"),
                        },
                    )
                    self.stats.identifiers_created += 1

                    # Store English translation content
                    if parsed["translation_en"]:
                        en_content = parsed["translation_en"]
                        await session.execute(
                            text("""
                                INSERT INTO text_contents (text_id, juan_num, content, char_count, lang)
                                VALUES (:text_id, 1, :content, :char_count, 'en')
                                ON CONFLICT ON CONSTRAINT uq_text_content_text_juan_lang DO UPDATE SET
                                    content = EXCLUDED.content,
                                    char_count = EXCLUDED.char_count
                            """),
                            {
                                "text_id": text_id,
                                "content": en_content,
                                "char_count": len(en_content),
                            },
                        )
                        self.stats.contents_created += 1

                        es_content_actions.append({
                            "_index": CONTENT_INDEX_NAME,
                            "_id": f"{text_id}_1_en",
                            "_source": {
                                "text_id": text_id,
                                "cbeta_id": cbeta_id,
                                "title_zh": title_en,
                                "juan_num": 1,
                                "content": en_content[:50000],
                                "char_count": len(en_content),
                                "lang": "en",
                                "source_code": "84000",
                            },
                        })

                    # Update char count
                    total_chars = len(parsed.get("translation_en", ""))
                    if total_chars:
                        await session.execute(
                            text("UPDATE buddhist_texts SET content_char_count = :cc WHERE id = :id"),
                            {"id": text_id, "cc": total_chars},
                        )

                    es_text_actions.append({
                        "_index": INDEX_NAME,
                        "_id": str(text_id),
                        "_source": {
                            "id": text_id,
                            "cbeta_id": cbeta_id,
                            "title_zh": title_en,
                            "title_en": title_en,
                            "title_bo": title_bo,
                            "title_sa": title_sa,
                            "lang": "bo",
                            "source_code": "84000",
                        },
                    })

                except Exception as e:
                    self.stats.errors += 1
                    print(f"  Error importing toh{toh}: {e}")

                if (i + 1) % 10 == 0:
                    await session.flush()
                    print(f"  Progress: {i + 1}/{len(texts)}, {self.stats.summary()}")

            await session.commit()

        # Bulk ES
        if es_text_actions:

            async def gen_t():
                for a in es_text_actions:
                    yield a

            async def gen_c():
                for a in es_content_actions:
                    yield a

            s1, _ = await async_bulk(self.es, gen_t(), raise_on_error=False)
            s2, _ = await async_bulk(self.es, gen_c(), raise_on_error=False)
            print(f"  ES: indexed {s1} texts, {s2} contents")


async def main():
    parser = argparse.ArgumentParser(description="Import 84000 translations")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of texts")
    parser.add_argument("--local-dir", type=str, help="Use local TEI XML directory")
    args = parser.parse_args()

    importer = Import84000(limit=args.limit, local_dir=args.local_dir)
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
