"""
Import Bibliotheca Polyglotta parallel texts.

Bibliotheca Polyglotta (University of Oslo) provides multilingual parallel
texts of Buddhist scriptures with segment-level alignment.

Usage:
    python scripts/import_polyglotta.py
    python scripts/import_polyglotta.py --limit 10
"""

import argparse
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.base_importer import BaseImporter

from sqlalchemy import select, text

from app.models.text import BuddhistText


POLYGLOTTA_BASE = "https://www2.hf.uio.no/polyglotta"


class PolyglottaImporter(BaseImporter):
    SOURCE_CODE = "polyglotta"
    SOURCE_NAME_ZH = "多语种佛典图书馆"
    SOURCE_NAME_EN = "Bibliotheca Polyglotta"
    SOURCE_BASE_URL = POLYGLOTTA_BASE
    SOURCE_DESCRIPTION = "奥斯陆大学多语种平行文本，含佛教经典多语对照"
    RATE_LIMIT_DELAY = 2.0

    def __init__(self, limit: int = 0):
        super().__init__()
        self.limit = limit

    async def discover_texts(self) -> list[dict]:
        """Discover available texts from Bibliotheca Polyglotta."""
        print("  Fetching Polyglotta index...")
        texts = []

        try:
            resp = await self.rate_limited_get(f"{POLYGLOTTA_BASE}/index.php")
            html = resp.text

            # Extract links to Buddhist text pages
            for match in re.finditer(
                r'href="(index\.php\?page=(?:volume|text|fulltext)&[^"]*id=(\d+)[^"]*)"[^>]*>([^<]+)',
                html,
            ):
                url_path = match.group(1)
                text_id = match.group(2)
                title = match.group(3).strip()

                if any(kw in title.lower() for kw in [
                    "sutra", "sutta", "lotus", "heart", "diamond",
                    "prajnaparamita", "vimalakirti", "lankavatara",
                    "saddharm", "buddhist", "pali", "sanskrit",
                ]):
                    texts.append({
                        "poly_id": text_id,
                        "title": title,
                        "url": f"{POLYGLOTTA_BASE}/{url_path}",
                    })

        except Exception as e:
            print(f"  Could not fetch Polyglotta index: {e}")
            # Known texts
            known = [
                {"poly_id": "1", "title": "Saddharmapuṇḍarīka (Lotus Sutra)", "url": f"{POLYGLOTTA_BASE}/index.php?page=volume&id=1"},
                {"poly_id": "2", "title": "Vajracchedikā (Diamond Sutra)", "url": f"{POLYGLOTTA_BASE}/index.php?page=volume&id=2"},
                {"poly_id": "3", "title": "Vimalakīrtinirdeśa", "url": f"{POLYGLOTTA_BASE}/index.php?page=volume&id=3"},
            ]
            texts = known

        print(f"  Discovered {len(texts)} Polyglotta texts.")
        return texts

    async def run_import(self):
        texts = await self.discover_texts()

        if self.limit > 0:
            texts = texts[:self.limit]

        if not texts:
            print("  No texts found to import.")
            return

        print(f"\n  Processing {len(texts)} Polyglotta texts...")

        async with self.session_factory() as session:
            source = await self.ensure_source(session)

            for i, info in enumerate(texts):
                poly_id = info["poly_id"]
                title = info["title"]

                try:
                    # Fetch the text page to discover available languages
                    resp = await self.rate_limited_get(info["url"])
                    html = resp.text

                    # Extract parallel segments
                    # Polyglotta uses tables with parallel columns
                    segments = self._extract_parallel_segments(html)

                    if not segments:
                        self.stats.skipped += 1
                        continue

                    # Create alignment task for this parallel text
                    await session.execute(
                        text("""
                            INSERT INTO text_identifiers
                                (text_id, source_id, source_uid, source_url)
                            SELECT bt.id, :source_id, :uid, :url
                            FROM buddhist_texts bt
                            WHERE bt.cbeta_id LIKE :pattern
                            LIMIT 1
                            ON CONFLICT ON CONSTRAINT uq_text_identifier_source_uid DO NOTHING
                        """),
                        {
                            "source_id": source.id,
                            "uid": f"poly-{poly_id}",
                            "url": info["url"],
                            "pattern": f"%{title.split('(')[0].strip()[:20]}%",
                        },
                    )
                    self.stats.identifiers_created += 1

                    # If we found segments, create alignment pairs
                    if len(segments) > 1:
                        # We'd ideally match texts and create AlignmentTask+AlignmentPair
                        # For now, just log the discovery
                        print(f"  [{poly_id}] {title}: {len(segments)} parallel segments found")

                except Exception as e:
                    self.stats.errors += 1
                    print(f"  Error processing poly-{poly_id}: {e}")

                if (i + 1) % 5 == 0:
                    await session.flush()

            await session.commit()

        print(f"  Polyglotta import done: {self.stats.summary()}")

    def _extract_parallel_segments(self, html: str) -> list[dict]:
        """Extract parallel text segments from Polyglotta HTML."""
        segments = []

        # Polyglotta uses table rows with parallel text in different languages
        rows = re.findall(
            r'<tr[^>]*class="[^"]*text[^"]*"[^>]*>(.*?)</tr>',
            html, re.DOTALL,
        )

        for row in rows:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            if len(cells) >= 2:
                # Clean HTML
                clean_cells = []
                for cell in cells:
                    cell_text = re.sub(r'<[^>]+>', '', cell).strip()
                    if cell_text:
                        clean_cells.append(cell_text)

                if len(clean_cells) >= 2:
                    segments.append({
                        "texts": clean_cells,
                    })

        return segments


async def main():
    parser = argparse.ArgumentParser(description="Import Bibliotheca Polyglotta")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of texts")
    args = parser.parse_args()

    importer = PolyglottaImporter(limit=args.limit)
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
