"""
Import Korean Tripitaka (高丽大藏经) IIIF manifests and identifiers.

The Koreana Tripitaka is available through the Korean National Library
with IIIF image manifests. This script maps CBETA K-series texts to
Korean Tripitaka identifiers and imports IIIF manifests for page images.

Usage:
    python scripts/import_korean_tripitaka.py
    python scripts/import_korean_tripitaka.py --limit 100
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


KTK_BASE = "https://kb.nl.go.kr"
KTK_IIIF_BASE = "https://lod.nl.go.kr/iiif"


class KoreanTripitakaImporter(BaseImporter):
    SOURCE_CODE = "ktk"
    SOURCE_NAME_ZH = "高丽大藏经"
    SOURCE_NAME_EN = "Koreana Tripitaka (Palman Daejanggyeong)"
    SOURCE_BASE_URL = KTK_BASE
    SOURCE_DESCRIPTION = "韩国国家图书馆数字化的高丽大藏经影像与元数据"
    RATE_LIMIT_DELAY = 1.5

    def __init__(self, limit: int = 0):
        super().__init__()
        self.limit = limit

    async def run_import(self):
        """Map CBETA K-series to Korean Tripitaka and add IIIF manifests."""
        print("\n  Linking Korean Tripitaka to CBETA K-series...")

        async with self.session_factory() as session:
            source = await self.ensure_source(session)

            # Get all K-series texts
            result = await session.execute(
                select(BuddhistText)
                .where(BuddhistText.cbeta_id.startswith("K"))
                .order_by(BuddhistText.cbeta_id)
            )
            k_texts = list(result.scalars().all())

            if self.limit > 0:
                k_texts = k_texts[:self.limit]

            print(f"  Found {len(k_texts)} K-series texts to process.")

            if not k_texts:
                print("  No K-series texts found. Run import_catalog.py first.")
                return

            for i, bt in enumerate(k_texts):
                # Extract K number
                m = re.match(r"K(\d+)", bt.cbeta_id)
                if not m:
                    continue

                k_num = m.group(1)

                # Add TextIdentifier for KTK
                await session.execute(
                    text("""
                        INSERT INTO text_identifiers (text_id, source_id, source_uid, source_url)
                        VALUES (:text_id, :source_id, :uid, :url)
                        ON CONFLICT ON CONSTRAINT uq_text_identifier_source_uid DO NOTHING
                    """),
                    {
                        "text_id": bt.id,
                        "source_id": source.id,
                        "uid": f"K{k_num}",
                        "url": f"{KTK_BASE}/resource/K{k_num}",
                    },
                )
                self.stats.identifiers_created += 1

                # Add IIIF manifest (if not already exists)
                manifest_url = f"{KTK_IIIF_BASE}/K{k_num}/manifest.json"
                existing_manifest = await session.execute(
                    text("""
                        SELECT id FROM iiif_manifests
                        WHERE text_id = :text_id AND source_id = :source_id
                    """),
                    {"text_id": bt.id, "source_id": source.id},
                )
                if not existing_manifest.fetchone():
                    await session.execute(
                        text("""
                            INSERT INTO iiif_manifests
                                (text_id, source_id, label, manifest_url, provider)
                            VALUES (:text_id, :source_id, :label, :url, 'Korean National Library')
                        """),
                        {
                            "text_id": bt.id,
                            "source_id": source.id,
                            "label": f"高丽大藏经 K{k_num} 影像",
                            "url": manifest_url,
                        },
                    )

                if (i + 1) % 500 == 0:
                    await session.flush()
                    print(f"  Progress: {i + 1}/{len(k_texts)}")

            await session.commit()

        print(f"  Korean Tripitaka import done: {self.stats.identifiers_created} identifiers.")


async def main():
    parser = argparse.ArgumentParser(description="Import Korean Tripitaka")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of texts")
    args = parser.parse_args()

    importer = KoreanTripitakaImporter(limit=args.limit)
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
