"""
Import SAT (Saṃgaṇikīkṛtaṃ Taiśotripiṭakaṃ) cross-references and IIIF manifests.

SAT provides a web-based version of the Taishō canon with page images.
This script does NOT create new BuddhistText records (they overlap with CBETA T-series).
Instead, it adds TextIdentifier mappings and IIIF manifests.

Usage:
    python scripts/import_sat.py
    python scripts/import_sat.py --limit 100
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


SAT_BASE = "https://21dzk.l.u-tokyo.ac.jp/SAT"
SAT_IIIF_BASE = "https://dzkimgs.l.u-tokyo.ac.jp/iiif"


class SATImporter(BaseImporter):
    SOURCE_CODE = "sat"
    SOURCE_NAME_ZH = "SAT 大正藏数据库"
    SOURCE_NAME_EN = "SAT Daizōkyō Text Database"
    SOURCE_BASE_URL = SAT_BASE
    SOURCE_API_URL = f"{SAT_BASE}/sat2018/master30.php"
    SOURCE_DESCRIPTION = "东京大学大正新脩大藏经文本数据库，提供页面影像和文本对照"
    RATE_LIMIT_DELAY = 1.5

    def __init__(self, limit: int = 0):
        super().__init__()
        self.limit = limit

    async def run_import(self):
        """Link existing CBETA T-series texts with SAT identifiers and IIIF."""
        print("\n  Linking SAT identifiers to CBETA T-series...")

        async with self.session_factory() as session:
            source = await self.ensure_source(session)

            # Get all T-series texts from DB
            result = await session.execute(
                select(BuddhistText)
                .where(BuddhistText.cbeta_id.startswith("T"))
                .order_by(BuddhistText.cbeta_id)
            )
            t_texts = list(result.scalars().all())

            if self.limit > 0:
                t_texts = t_texts[:self.limit]

            print(f"  Found {len(t_texts)} T-series texts to process.")

            for i, bt in enumerate(t_texts):
                # Extract T number: T0001 → 0001
                m = re.match(r"T(\d+)", bt.cbeta_id)
                if not m:
                    continue

                t_num = m.group(1)

                # SAT URL format
                sat_url = f"{SAT_BASE}/sat2018/entry2.cgi?sno={t_num}"

                # Add TextIdentifier for SAT
                await session.execute(
                    text("""
                        INSERT INTO text_identifiers (text_id, source_id, source_uid, source_url)
                        VALUES (:text_id, :source_id, :uid, :url)
                        ON CONFLICT ON CONSTRAINT uq_text_identifier_source_uid DO NOTHING
                    """),
                    {
                        "text_id": bt.id,
                        "source_id": source.id,
                        "uid": f"T{t_num}",
                        "url": sat_url,
                    },
                )
                self.stats.identifiers_created += 1

                # Add IIIF manifest reference (if not already exists)
                iiif_manifest_url = f"{SAT_IIIF_BASE}/manifest/SAT_T{t_num}.json"

                # Check if manifest already exists for this text+source
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
                            VALUES (:text_id, :source_id, :label, :url, 'SAT')
                        """),
                        {
                            "text_id": bt.id,
                            "source_id": source.id,
                            "label": f"SAT T{t_num} Page Images",
                            "url": iiif_manifest_url,
                        },
                    )

                if (i + 1) % 500 == 0:
                    await session.flush()
                    print(f"  Progress: {i + 1}/{len(t_texts)}")

            await session.commit()

        print(f"  SAT import done: {self.stats.identifiers_created} identifiers created.")


async def main():
    parser = argparse.ArgumentParser(description="Import SAT cross-references")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of texts")
    args = parser.parse_args()

    importer = SATImporter(limit=args.limit)
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
