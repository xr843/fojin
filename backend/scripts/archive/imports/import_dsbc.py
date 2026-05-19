"""
Import DSBC (Digital Sanskrit Buddhist Canon) texts.

The DSBC project (dsbcproject.org) provides Sanskrit Buddhist texts
maintained by the Nagarjuna Institute.

Usage:
    python scripts/import_dsbc.py
    python scripts/import_dsbc.py --limit 10
    python scripts/import_dsbc.py --local-dir data/dsbc
"""

import argparse
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.base_importer import BaseImporter

from sqlalchemy import select, text
from elasticsearch.helpers import async_bulk

from app.core.elasticsearch import INDEX_NAME, CONTENT_INDEX_NAME
from app.models.text import BuddhistText


DSBC_BASE = "https://www.dsbcproject.org"


class DSBCImporter(BaseImporter):
    SOURCE_CODE = "dsbc"
    SOURCE_NAME_ZH = "数字梵文佛典"
    SOURCE_NAME_EN = "Digital Sanskrit Buddhist Canon"
    SOURCE_BASE_URL = DSBC_BASE
    SOURCE_DESCRIPTION = "由Nagarjuna Institute维护的数字梵文佛教典藏"
    RATE_LIMIT_DELAY = 2.0

    def __init__(self, limit: int = 0, local_dir: str | None = None):
        super().__init__()
        self.limit = limit
        self.local_dir = local_dir

    async def discover_texts(self) -> list[dict]:
        """Discover DSBC texts from their website or local directory."""
        if self.local_dir and os.path.isdir(self.local_dir):
            texts = []
            for f in sorted(os.listdir(self.local_dir)):
                if f.endswith((".xml", ".txt", ".htm", ".html")):
                    texts.append({
                        "filename": f,
                        "local_path": os.path.join(self.local_dir, f),
                    })
            print(f"  Found {len(texts)} local files in {self.local_dir}")
            return texts

        # Try to fetch the canon index
        print("  Fetching DSBC canon index...")
        texts = []

        try:
            resp = await self.rate_limited_get(f"{DSBC_BASE}/canon-punctuation")
            html = resp.text

            # Extract links to individual text pages
            for match in re.finditer(
                r'href="(/canon-punctuation/content/(?:sr|uv|ds|sp|vk|lv|abh|bc|sdk|mvs|[^"]+))"[^>]*>([^<]+)',
                html,
            ):
                path = match.group(1)
                title = match.group(2).strip()
                text_id = path.split("/")[-1]
                texts.append({
                    "url": f"{DSBC_BASE}{path}",
                    "dsbc_id": text_id,
                    "title": title,
                })

        except Exception as e:
            print(f"  Could not fetch DSBC index: {e}")
            print("  Trying alternative approach...")

            # Fallback: try known text paths
            known_texts = [
                ("sr", "Saddharmapuṇḍarīka"),
                ("vk", "Vimalakīrtinirdeśa"),
                ("lv", "Lalitavistara"),
                ("sp", "Sukhāvatīvyūha (shorter)"),
                ("bc", "Buddhacarita"),
                ("sdk", "Śikṣāsamuccaya"),
                ("ds", "Daśabhūmika"),
                ("abh", "Abhidharmakośa"),
                ("mvs", "Mahāvastu"),
            ]
            for text_id, title in known_texts:
                texts.append({
                    "url": f"{DSBC_BASE}/canon-punctuation/content/{text_id}",
                    "dsbc_id": text_id,
                    "title": title,
                })

        print(f"  Discovered {len(texts)} DSBC texts.")
        return texts

    def extract_text_content(self, html: str) -> str:
        """Extract Sanskrit text content from DSBC HTML page."""
        # Remove HTML tags but keep text
        text_content = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        text_content = re.sub(r'<style[^>]*>.*?</style>', '', text_content, flags=re.DOTALL)

        # Try to find the main content area
        main_match = re.search(
            r'<div[^>]*class="[^"]*(?:content|text|body)[^"]*"[^>]*>(.*?)</div>',
            text_content, flags=re.DOTALL | re.IGNORECASE,
        )
        if main_match:
            text_content = main_match.group(1)

        # Remove remaining HTML tags
        text_content = re.sub(r'<[^>]+>', ' ', text_content)
        # Clean up whitespace
        text_content = re.sub(r'\s+', ' ', text_content).strip()

        return text_content

    async def run_import(self):
        texts = await self.discover_texts()

        if self.limit > 0:
            texts = texts[:self.limit]

        if not texts:
            print("  No texts found to import.")
            return

        print(f"\n  Importing {len(texts)} DSBC texts...")

        async with self.session_factory() as session:
            source = await self.ensure_source(session)
            es_text_actions = []
            es_content_actions = []

            for i, info in enumerate(texts):
                dsbc_id = info.get("dsbc_id", os.path.splitext(info.get("filename", ""))[0])
                cbeta_id = f"DSBC-{dsbc_id}"
                title = info.get("title", dsbc_id)

                try:
                    # Get content
                    if info.get("local_path"):
                        with open(info["local_path"], "r", encoding="utf-8", errors="replace") as f:
                            raw = f.read()
                        content = raw
                    else:
                        resp = await self.rate_limited_get(info["url"])
                        raw = resp.text
                        content = self.extract_text_content(raw)

                    if not content.strip() or len(content.strip()) < 100:
                        self.stats.skipped += 1
                        continue

                    char_count = len(content.strip())

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
                            "title_zh": title,
                            "title_sa": title,
                            "source_id": source.id,
                            "char_count": char_count,
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
                            "uid": dsbc_id,
                            "url": info.get("url", f"{DSBC_BASE}/canon-punctuation/content/{dsbc_id}"),
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
                            "content": content.strip(),
                            "char_count": char_count,
                        },
                    )
                    self.stats.contents_created += 1

                    # Try to create parallel relation with CBETA
                    await self._try_create_parallel(session, text_id, title)

                    es_text_actions.append({
                        "_index": INDEX_NAME,
                        "_id": str(text_id),
                        "_source": {
                            "id": text_id,
                            "cbeta_id": cbeta_id,
                            "title_zh": title,
                            "title_sa": title,
                            "lang": "sa",
                            "source_code": "dsbc",
                        },
                    })
                    es_content_actions.append({
                        "_index": CONTENT_INDEX_NAME,
                        "_id": f"{text_id}_1_sa",
                        "_source": {
                            "text_id": text_id,
                            "cbeta_id": cbeta_id,
                            "title_zh": title,
                            "juan_num": 1,
                            "content": content.strip()[:50000],  # Limit for ES
                            "char_count": char_count,
                            "lang": "sa",
                            "source_code": "dsbc",
                        },
                    })

                except Exception as e:
                    self.stats.errors += 1
                    print(f"  Error importing {dsbc_id}: {e}")

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

    async def _try_create_parallel(self, session, dsbc_text_id: int, title: str):
        """Try to create parallel relation with CBETA Chinese translations."""
        # Well-known Sanskrit-Chinese parallel mappings
        known_parallels = {
            "Saddharmapuṇḍarīka": "T0262",
            "Vimalakīrtinirdeśa": "T0475",
            "Lalitavistara": "T0186",
            "Buddhacarita": "T0192",
            "Sukhāvatīvyūha": "T0366",
            "Daśabhūmika": "T0286",
            "Vajracchedikā": "T0235",
            "Laṅkāvatāra": "T0670",
            "Aṣṭasāhasrikā": "T0227",
        }

        for key, cbeta_id in known_parallels.items():
            if key.lower() in title.lower():
                result = await session.execute(
                    select(BuddhistText.id).where(BuddhistText.cbeta_id == cbeta_id)
                )
                match_id = result.scalar_one_or_none()
                if match_id:
                    await session.execute(
                        text("""
                            INSERT INTO text_relations
                                (text_a_id, text_b_id, relation_type, source, confidence)
                            VALUES (:a, :b, 'parallel', 'dsbc', 0.9)
                            ON CONFLICT ON CONSTRAINT uq_text_relation DO NOTHING
                        """),
                        {"a": dsbc_text_id, "b": match_id},
                    )
                    self.stats.relations_created += 1
                break


async def main():
    parser = argparse.ArgumentParser(description="Import DSBC Sanskrit Buddhist texts")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of texts")
    parser.add_argument("--local-dir", type=str, help="Use local directory")
    args = parser.parse_args()

    importer = DSBCImporter(limit=args.limit, local_dir=args.local_dir)
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
