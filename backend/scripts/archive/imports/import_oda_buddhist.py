"""
Import 织田得能《佛教大辞典》(Oda Tokunō Buddhist Dictionary).

Source: NDL / Archive.org scans → OCR
Status: Data source is scan-only (OCR required). This script serves as a
        placeholder/skeleton for future OCR-based import.

Currently imports nothing — prints a notice about data source limitations.

Usage:
    python scripts/import_oda_buddhist.py
    python scripts/import_oda_buddhist.py --limit 100
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.base_importer import BaseImporter


class OdaBuddhistImporter(BaseImporter):
    SOURCE_CODE = "oda-bukkyou"
    SOURCE_NAME_ZH = "织田佛教大辞典"
    SOURCE_NAME_EN = "Oda Tokunō Buddhist Dictionary"
    SOURCE_BASE_URL = ""
    SOURCE_DESCRIPTION = "织田得能《佛教大辞典》(1917), Japanese Buddhist dictionary — pending OCR digitization"
    RATE_LIMIT_DELAY = 0.5

    def __init__(self, limit: int = 0):
        super().__init__()
        self.limit = limit

    async def run_import(self):
        print("  ⚠ 织田《佛教大辞典》currently has no structured digital source.")
        print("  The original is available only as scanned images from NDL/Archive.org.")
        print("  OCR digitization would be required to produce structured entries.")
        print("  This importer is a placeholder for future work.")
        print()
        print("  Potential approaches:")
        print("    1. OCR with Tesseract (jpn_vert) on Archive.org scans")
        print("    2. Find an existing OCR'd dataset from academic projects")
        print("    3. Manual transcription of key entries")
        print()
        print("  Skipping import — no data available.")
        self.stats.skipped = 1


async def main():
    parser = argparse.ArgumentParser(description="Import 织田佛教大辞典 (placeholder)")
    parser.add_argument("--limit", type=int, default=0, help="Limit entries")
    args = parser.parse_args()

    importer = OdaBuddhistImporter(limit=args.limit)
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
