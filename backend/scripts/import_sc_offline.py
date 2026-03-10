"""
Import SuttaCentral data from locally downloaded bilara-data files.

Reads from:
  - data/sc_download/catalog.json (sutta list from suttaplex API)
  - data/bilara-data/root/pli/  (Pali root text, segmented JSON)
  - data/bilara-data/translation/en/  (English translations, segmented JSON)

Usage:
    python scripts/import_sc_offline.py
    python scripts/import_sc_offline.py --limit 100
    python scripts/import_sc_offline.py --content-only
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.base_importer import BaseImporter

from sqlalchemy import select, text
from elasticsearch.helpers import async_bulk

from app.core.elasticsearch import INDEX_NAME, CONTENT_INDEX_NAME
from app.models.text import BuddhistText


DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
SC_CATALOG = os.path.join(DATA_DIR, "sc_download", "catalog.json")
BILARA_ROOT = os.path.join(DATA_DIR, "bilara-data", "root", "pli")
BILARA_TRANS = os.path.join(DATA_DIR, "bilara-data", "translation", "en")


def find_bilara_file(uid: str, base_dir: str, pattern_suffix: str) -> str | None:
    """Find a bilara JSON file matching a sutta UID."""
    # uid like "dn1", "sn1.1", "an1.1-10" etc.
    # file like "dn1_root-pli-ms.json" or "sn1.1_translation-en-sujato.json"
    base = Path(base_dir)
    if not base.exists():
        return None

    # Search recursively for matching file
    for json_file in base.rglob(f"{uid}_{pattern_suffix}*.json"):
        return str(json_file)

    # Try with period replaced (some UIDs have dots)
    return None


def load_bilara_text(filepath: str) -> str:
    """Load bilara segmented JSON and join into plain text."""
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        return "\n".join(v for v in data.values() if v and v.strip())
    return ""


# Pre-build file index for fast lookup
def build_file_index(base_dir: str, pattern_suffix: str) -> dict[str, str]:
    """Build uid -> filepath mapping."""
    index = {}
    base = Path(base_dir)
    if not base.exists():
        return index

    for json_file in base.rglob(f"*_{pattern_suffix}*.json"):
        # Extract uid from filename: "dn1_root-pli-ms.json" -> "dn1"
        name = json_file.stem  # "dn1_root-pli-ms"
        uid = name.split(f"_{pattern_suffix}")[0]
        if uid:
            index[uid] = str(json_file)

    return index


class SuttaCentralOfflineImporter(BaseImporter):
    SOURCE_CODE = "suttacentral"
    SOURCE_NAME_ZH = "SuttaCentral 巴利经藏"
    SOURCE_NAME_EN = "SuttaCentral"
    SOURCE_BASE_URL = "https://suttacentral.net"
    SOURCE_API_URL = "https://suttacentral.net/api"
    SOURCE_DESCRIPTION = "Early Buddhist texts, translations, and parallels"
    RATE_LIMIT_DELAY = 0

    def __init__(self, limit: int = 0, content_only: bool = False):
        super().__init__()
        self.limit = limit
        self.content_only = content_only

    async def phase_a_catalog(self):
        """Import catalog from local catalog.json."""
        print("\n[Phase A] Importing SuttaCentral catalog...")

        if not os.path.exists(SC_CATALOG):
            print(f"  ERROR: {SC_CATALOG} not found. Run download_sc_data.py first.")
            return

        with open(SC_CATALOG) as f:
            suttas = json.load(f)

        if self.limit > 0:
            suttas = suttas[:self.limit]

        print(f"  Loaded {len(suttas)} suttas from catalog.")

        async with self.session_factory() as session:
            source = await self.ensure_source(session)
            es_actions = []

            for i, sutta in enumerate(suttas):
                uid = sutta["uid"]
                cbeta_id = f"SC-{uid}"
                original_title = sutta.get("original_title", "")
                translated_title = sutta.get("translated_title", "")
                title_zh = translated_title or original_title or uid
                title_pi = original_title or None
                title_en = translated_title or None

                result = await session.execute(
                    text("""
                        INSERT INTO buddhist_texts
                            (cbeta_id, title_zh, title_pi, title_en, source_id, lang, has_content)
                        VALUES (:cbeta_id, :title_zh, :title_pi, :title_en, :source_id, 'pi', false)
                        ON CONFLICT (cbeta_id) DO UPDATE SET
                            title_zh = EXCLUDED.title_zh,
                            title_pi = COALESCE(EXCLUDED.title_pi, buddhist_texts.title_pi),
                            title_en = COALESCE(EXCLUDED.title_en, buddhist_texts.title_en)
                        RETURNING id
                    """),
                    {
                        "cbeta_id": cbeta_id,
                        "title_zh": title_zh,
                        "title_pi": title_pi,
                        "title_en": title_en,
                        "source_id": source.id,
                    },
                )
                text_id = result.scalar_one()

                await session.execute(
                    text("""
                        INSERT INTO text_identifiers (text_id, source_id, source_uid, source_url)
                        VALUES (:text_id, :source_id, :uid, :url)
                        ON CONFLICT ON CONSTRAINT uq_text_identifier_source_uid DO NOTHING
                    """),
                    {
                        "text_id": text_id,
                        "source_id": source.id,
                        "uid": uid,
                        "url": f"https://suttacentral.net/{uid}",
                    },
                )

                es_actions.append({
                    "_index": INDEX_NAME,
                    "_id": str(text_id),
                    "_source": {
                        "id": text_id,
                        "cbeta_id": cbeta_id,
                        "title_zh": title_zh,
                        "title_pi": title_pi,
                        "title_en": title_en,
                        "lang": "pi",
                        "source_code": "suttacentral",
                    },
                })

                self.stats.texts_created += 1

                if (i + 1) % 500 == 0:
                    await session.flush()
                    print(f"  Catalog: {i + 1}/{len(suttas)}")

            await session.commit()

        if es_actions:
            async def gen():
                for a in es_actions:
                    yield a
            success, _ = await async_bulk(self.es, gen(), raise_on_error=False)
            print(f"  ES indexed: {success}")

        print(f"  Phase A done: {self.stats.texts_created} texts.")

    async def phase_b_content(self):
        """Import content from bilara-data files."""
        print("\n[Phase B] Importing content from bilara-data...")

        # Build file indices
        print("  Building file index...")
        pali_index = build_file_index(BILARA_ROOT, "root")
        en_index = build_file_index(BILARA_TRANS, "translation")
        print(f"  Pali files: {len(pali_index)}, English files: {len(en_index)}")

        async with self.session_factory() as session:
            source = await self.ensure_source(session)
            result = await session.execute(
                select(BuddhistText)
                .where(BuddhistText.source_id == source.id)
                .order_by(BuddhistText.cbeta_id)
            )
            all_texts = list(result.scalars().all())

        if self.limit > 0:
            all_texts = all_texts[:self.limit]

        print(f"  Processing {len(all_texts)} texts...")

        es_content_actions = []

        for i, bt in enumerate(all_texts):
            uid = bt.cbeta_id.replace("SC-", "")

            pali_file = pali_index.get(uid)
            en_file = en_index.get(uid)

            if not pali_file and not en_file:
                self.stats.skipped += 1
                continue

            pali_text = load_bilara_text(pali_file) if pali_file else ""
            en_text = load_bilara_text(en_file) if en_file else ""

            async with self.session_factory() as session:
                if pali_text.strip():
                    await session.execute(
                        text("""
                            INSERT INTO text_contents (text_id, juan_num, content, char_count, lang)
                            VALUES (:text_id, 1, :content, :char_count, 'pi')
                            ON CONFLICT ON CONSTRAINT uq_text_content_text_juan_lang DO UPDATE SET
                                content = EXCLUDED.content,
                                char_count = EXCLUDED.char_count
                        """),
                        {
                            "text_id": bt.id,
                            "content": pali_text.strip(),
                            "char_count": len(pali_text.strip()),
                        },
                    )
                    self.stats.contents_created += 1

                    es_content_actions.append({
                        "_index": CONTENT_INDEX_NAME,
                        "_id": f"{bt.id}_1_pi",
                        "_source": {
                            "text_id": bt.id,
                            "cbeta_id": bt.cbeta_id,
                            "title_zh": bt.title_zh,
                            "juan_num": 1,
                            "content": pali_text.strip()[:50000],
                            "char_count": len(pali_text.strip()),
                            "lang": "pi",
                            "source_code": "suttacentral",
                        },
                    })

                if en_text.strip():
                    await session.execute(
                        text("""
                            INSERT INTO text_contents (text_id, juan_num, content, char_count, lang)
                            VALUES (:text_id, 1, :content, :char_count, 'en')
                            ON CONFLICT ON CONSTRAINT uq_text_content_text_juan_lang DO UPDATE SET
                                content = EXCLUDED.content,
                                char_count = EXCLUDED.char_count
                        """),
                        {
                            "text_id": bt.id,
                            "content": en_text.strip(),
                            "char_count": len(en_text.strip()),
                        },
                    )
                    self.stats.contents_created += 1

                    es_content_actions.append({
                        "_index": CONTENT_INDEX_NAME,
                        "_id": f"{bt.id}_1_en",
                        "_source": {
                            "text_id": bt.id,
                            "cbeta_id": bt.cbeta_id,
                            "title_zh": bt.title_zh,
                            "juan_num": 1,
                            "content": en_text.strip()[:50000],
                            "char_count": len(en_text.strip()),
                            "lang": "en",
                            "source_code": "suttacentral",
                        },
                    })

                if pali_text.strip() or en_text.strip():
                    char_count = len(pali_text.strip()) + len(en_text.strip())
                    await session.execute(
                        text("""
                            UPDATE buddhist_texts SET has_content = true, content_char_count = :cc
                            WHERE id = :id
                        """),
                        {"id": bt.id, "cc": char_count},
                    )

                await session.commit()

            if (i + 1) % 500 == 0:
                print(f"  Content: {i + 1}/{len(all_texts)}, "
                      f"contents={self.stats.contents_created}, skipped={self.stats.skipped}")

        # Bulk ES index
        if es_content_actions:
            async def gen_c():
                for a in es_content_actions:
                    yield a
            success, _ = await async_bulk(self.es, gen_c(), raise_on_error=False, chunk_size=500)
            print(f"  ES content indexed: {success}")

        print(f"  Phase B done: {self.stats.contents_created} contents, "
              f"{self.stats.skipped} skipped.")

    async def run_import(self):
        if self.content_only:
            await self.phase_b_content()
        else:
            await self.phase_a_catalog()
            await self.phase_b_content()


async def main():
    parser = argparse.ArgumentParser(description="Import SuttaCentral from local bilara-data")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--content-only", action="store_true")
    args = parser.parse_args()

    importer = SuttaCentralOfflineImporter(
        limit=args.limit,
        content_only=args.content_only,
    )
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
