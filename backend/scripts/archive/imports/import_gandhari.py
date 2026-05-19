"""
Import Gandhari.org Gāndhārī language texts.

Gāndhārī is an ancient Middle Indo-Aryan language from the Gandhara region.
Gandhari.org catalogues manuscripts, inscriptions, and texts.

Usage:
    python scripts/import_gandhari.py
    python scripts/import_gandhari.py --limit 10
"""

import argparse
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.base_importer import BaseImporter

from sqlalchemy import text
from elasticsearch.helpers import async_bulk

from app.core.elasticsearch import INDEX_NAME


GANDHARI_BASE = "https://gandhari.org"


class GandhariImporter(BaseImporter):
    SOURCE_CODE = "gandhari"
    SOURCE_NAME_ZH = "犍陀罗语佛典"
    SOURCE_NAME_EN = "Gandhari.org"
    SOURCE_BASE_URL = GANDHARI_BASE
    SOURCE_DESCRIPTION = "犍陀罗语（古代印度西北地区语言）佛教文献和铭文数据库"
    RATE_LIMIT_DELAY = 2.0

    def __init__(self, limit: int = 0):
        super().__init__()
        self.limit = limit

    async def discover_texts(self) -> list[dict]:
        """Discover Gāndhārī texts from gandhari.org."""
        print("  Fetching Gandhari.org catalog...")
        texts = []

        try:
            # Try the catalog/dictionary page
            resp = await self.rate_limited_get(f"{GANDHARI_BASE}/catalog")
            html = resp.text

            # Extract text entries
            for match in re.finditer(
                r'<a[^>]*href="(/catalog/([^"]+))"[^>]*>([^<]+)</a>',
                html,
            ):
                path = match.group(1)
                text_id = match.group(2)
                title = match.group(3).strip()

                texts.append({
                    "gand_id": text_id,
                    "title": title,
                    "url": f"{GANDHARI_BASE}{path}",
                })

        except Exception as e:
            print(f"  Could not fetch catalog: {e}")
            # Known Gāndhārī Buddhist manuscript collections
            known = [
                {"gand_id": "bajaur-collection", "title": "Bajaur Collection"},
                {"gand_id": "senior-collection", "title": "Senior Collection"},
                {"gand_id": "schøyen-collection", "title": "Schøyen Collection"},
                {"gand_id": "split-collection", "title": "Split Collection"},
                {"gand_id": "khotan-dharmapadha", "title": "Khotan Dharmapada"},
                {"gand_id": "gandharan-avadana", "title": "Gandhāran Avadāna"},
                {"gand_id": "british-library-scrolls", "title": "British Library Scrolls"},
                {"gand_id": "university-washington", "title": "University of Washington Collection"},
            ]
            for k in known:
                k["url"] = f"{GANDHARI_BASE}/catalog/{k['gand_id']}"
            texts = known

        print(f"  Discovered {len(texts)} Gāndhārī texts/collections.")
        return texts

    async def run_import(self):
        texts = await self.discover_texts()

        if self.limit > 0:
            texts = texts[:self.limit]

        if not texts:
            print("  No texts found.")
            return

        print(f"\n  Importing {len(texts)} Gāndhārī texts...")

        async with self.session_factory() as session:
            source = await self.ensure_source(session)
            es_actions = []

            for i, info in enumerate(texts):
                gand_id = info["gand_id"]
                cbeta_id = f"GAND-{gand_id}"
                title = info["title"]

                try:
                    # Upsert BuddhistText
                    result = await session.execute(
                        text("""
                            INSERT INTO buddhist_texts
                                (cbeta_id, title_zh, title_en, source_id, lang, has_content)
                            VALUES (:cbeta_id, :title_zh, :title_en, :source_id, 'pgd', false)
                            ON CONFLICT (cbeta_id) DO UPDATE SET
                                title_en = COALESCE(EXCLUDED.title_en, buddhist_texts.title_en)
                            RETURNING id
                        """),
                        {
                            "cbeta_id": cbeta_id,
                            "title_zh": title,
                            "title_en": title,
                            "source_id": source.id,
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
                            "uid": gand_id,
                            "url": info["url"],
                        },
                    )
                    self.stats.identifiers_created += 1

                    es_actions.append({
                        "_index": INDEX_NAME,
                        "_id": str(text_id),
                        "_source": {
                            "id": text_id,
                            "cbeta_id": cbeta_id,
                            "title_zh": title,
                            "title_en": title,
                            "lang": "pgd",
                            "source_code": "gandhari",
                        },
                    })

                except Exception as e:
                    self.stats.errors += 1
                    print(f"  Error: {gand_id}: {e}")

            await session.commit()

        # ES
        if es_actions:

            async def gen():
                for a in es_actions:
                    yield a

            s, _ = await async_bulk(self.es, gen(), raise_on_error=False)
            print(f"  ES: indexed {s} texts")


async def main():
    parser = argparse.ArgumentParser(description="Import Gandhari.org texts")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of texts")
    args = parser.parse_args()

    importer = GandhariImporter(limit=args.limit)
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
