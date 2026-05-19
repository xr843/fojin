"""
Import SuttaCentral full Pali canon via their API.

Three phases:
  A. Catalog: GET /api/menu — recursive extraction, no 500 limit
  B. Content: GET /api/suttas/{uid}/pali — Pali root + English translation
  C. Parallels: GET /api/suttaplex/{uid} — cross-reference with CBETA T-series

Usage:
    python scripts/import_suttacentral.py
    python scripts/import_suttacentral.py --content-only
    python scripts/import_suttacentral.py --parallels-only
    python scripts/import_suttacentral.py --limit 100
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.base_importer import BaseImporter

from sqlalchemy import select, text
from elasticsearch.helpers import async_bulk

from app.core.elasticsearch import INDEX_NAME, CONTENT_INDEX_NAME
from app.models.source import DataSource, TextIdentifier
from app.models.text import BuddhistText
from app.models.relation import TextRelation


SC_API_BASE = "https://suttacentral.net/api"


class SuttaCentralImporter(BaseImporter):
    SOURCE_CODE = "suttacentral"
    SOURCE_NAME_ZH = "SuttaCentral 巴利经藏"
    SOURCE_NAME_EN = "SuttaCentral"
    SOURCE_BASE_URL = "https://suttacentral.net"
    SOURCE_API_URL = SC_API_BASE
    SOURCE_DESCRIPTION = "Early Buddhist texts, translations, and parallels"
    RATE_LIMIT_DELAY = 1.0

    def __init__(self, limit: int = 0, content_only: bool = False, parallels_only: bool = False):
        super().__init__()
        self.limit = limit
        self.content_only = content_only
        self.parallels_only = parallels_only

    def extract_suttas(self, menu_data, depth=0) -> list[tuple[str, str, str]]:
        """Recursively extract (uid, root_name, translated_name) from SC menu."""
        results = []
        if isinstance(menu_data, list):
            for item in menu_data:
                results.extend(self.extract_suttas(item, depth + 1))
        elif isinstance(menu_data, dict):
            uid = menu_data.get("uid", "")
            root_name = menu_data.get("root_name") or ""
            translated_name = menu_data.get("translated_name") or ""
            children = menu_data.get("children", [])

            if uid and not children and depth > 1:
                results.append((uid, root_name, translated_name))

            for child in children:
                results.extend(self.extract_suttas(child, depth + 1))
        return results

    async def phase_a_catalog(self):
        """Phase A: Import full catalog from SC menu API."""
        print("\n[Phase A] Importing SuttaCentral catalog...")

        checkpoint = self.load_checkpoint()
        if checkpoint.get("phase_a_done"):
            print("  Phase A already completed (checkpoint). Skipping.")
            return

        resp = await self.rate_limited_get(f"{SC_API_BASE}/menu")
        menu = resp.json()
        suttas = self.extract_suttas(menu)
        print(f"  Extracted {len(suttas)} suttas from menu.")

        if self.limit > 0:
            suttas = suttas[:self.limit]

        async with self.session_factory() as session:
            source = await self.ensure_source(session)
            es_actions = []

            for i, (uid, root_name, translated_name) in enumerate(suttas):
                cbeta_id = f"SC-{uid}"
                title_zh = translated_name or root_name or uid
                title_pi = root_name or None
                title_en = translated_name or None

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
                    print(f"  Catalog: {i + 1}/{len(suttas)} processed...")

            await session.commit()

        # Bulk index to ES
        if es_actions:

            async def gen():
                for a in es_actions:
                    yield a

            success, _ = await async_bulk(self.es, gen(), raise_on_error=False)
            print(f"  ES indexed: {success}")

        self.save_checkpoint({"phase_a_done": True})
        print(f"  Phase A done: {self.stats.texts_created} texts imported.")

    async def phase_b_content(self):
        """Phase B: Fetch Pali root text and English translation for each sutta."""
        print("\n[Phase B] Importing SuttaCentral content...")

        checkpoint = self.load_checkpoint()
        last_uid = checkpoint.get("phase_b_last_uid")

        async with self.session_factory() as session:
            source = await self.ensure_source(session)

            # Get all SC texts
            result = await session.execute(
                select(BuddhistText)
                .where(BuddhistText.source_id == source.id)
                .order_by(BuddhistText.cbeta_id)
            )
            all_texts = list(result.scalars().all())

        # Resume
        if last_uid:
            skip = True
            filtered = []
            for bt in all_texts:
                uid = bt.cbeta_id.replace("SC-", "")
                if skip:
                    if uid == last_uid:
                        skip = False
                    continue
                filtered.append(bt)
            all_texts = filtered
            print(f"  Resuming after {last_uid}, {len(all_texts)} remaining.")

        if self.limit > 0:
            all_texts = all_texts[:self.limit]

        print(f"  Processing {len(all_texts)} texts for content...")

        for i, bt in enumerate(all_texts):
            uid = bt.cbeta_id.replace("SC-", "")

            try:
                # Fetch Pali text
                resp = await self.rate_limited_get(f"{SC_API_BASE}/suttas/{uid}/pali")
                data = resp.json()

                # Extract root (Pali) text
                root_text = ""
                translation_text = ""

                if isinstance(data, dict):
                    root = data.get("root_text") or data.get("text") or ""
                    if isinstance(root, dict):
                        root_text = "\n".join(root.values())
                    elif isinstance(root, str):
                        root_text = root

                    trans = data.get("translation") or ""
                    if isinstance(trans, dict):
                        translation_text = "\n".join(trans.values())
                    elif isinstance(trans, str):
                        translation_text = trans

                async with self.session_factory() as session:
                    # Store Pali content
                    if root_text.strip():
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
                                "content": root_text.strip(),
                                "char_count": len(root_text.strip()),
                            },
                        )
                        self.stats.contents_created += 1

                        # Index to ES
                        await self.es.index(
                            index=CONTENT_INDEX_NAME,
                            id=f"{bt.id}_1_pi",
                            document={
                                "text_id": bt.id,
                                "cbeta_id": bt.cbeta_id,
                                "title_zh": bt.title_zh,
                                "juan_num": 1,
                                "content": root_text.strip(),
                                "char_count": len(root_text.strip()),
                                "lang": "pi",
                                "source_code": "suttacentral",
                            },
                        )

                    # Store English translation
                    if translation_text.strip():
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
                                "content": translation_text.strip(),
                                "char_count": len(translation_text.strip()),
                            },
                        )
                        self.stats.contents_created += 1

                    # Update has_content
                    if root_text.strip() or translation_text.strip():
                        char_count = len(root_text.strip()) + len(translation_text.strip())
                        await session.execute(
                            text("""
                                UPDATE buddhist_texts SET has_content = true, content_char_count = :cc
                                WHERE id = :id
                            """),
                            {"id": bt.id, "cc": char_count},
                        )

                    await session.commit()

            except Exception as e:
                self.stats.errors += 1
                if "404" in str(e) or "Not Found" in str(e):
                    self.stats.skipped += 1
                else:
                    print(f"  Error for {uid}: {e}")

            if (i + 1) % 100 == 0:
                self.save_checkpoint({
                    "phase_a_done": True,
                    "phase_b_last_uid": uid,
                })
                print(f"  Content: {i + 1}/{len(all_texts)}, "
                      f"contents={self.stats.contents_created}, errors={self.stats.errors}")

        self.save_checkpoint({"phase_a_done": True, "phase_b_done": True})
        print(f"  Phase B done: {self.stats.contents_created} contents created.")

    async def phase_c_parallels(self):
        """Phase C: Create parallel relations with CBETA T-series."""
        print("\n[Phase C] Importing SuttaCentral parallels...")

        async with self.session_factory() as session:
            source = await self.ensure_source(session)

            result = await session.execute(
                select(BuddhistText)
                .where(BuddhistText.source_id == source.id)
                .order_by(BuddhistText.cbeta_id)
            )
            sc_texts = list(result.scalars().all())

        if self.limit > 0:
            sc_texts = sc_texts[:self.limit]

        print(f"  Checking parallels for {len(sc_texts)} SC texts...")

        for i, bt in enumerate(sc_texts):
            uid = bt.cbeta_id.replace("SC-", "")

            try:
                resp = await self.rate_limited_get(f"{SC_API_BASE}/suttaplex/{uid}")
                data = resp.json()

                parallels = data.get("parallels", []) if isinstance(data, dict) else []

                for par in parallels:
                    par_uid = par.get("uid", "") if isinstance(par, dict) else ""
                    # Match CBETA T-series (e.g., "t99" → "T0099")
                    if par_uid.startswith("t") and par_uid[1:].isdigit():
                        cbeta_match = f"T{par_uid[1:].zfill(4)}"

                        async with self.session_factory() as session:
                            result = await session.execute(
                                select(BuddhistText.id).where(
                                    BuddhistText.cbeta_id == cbeta_match
                                )
                            )
                            match_id = result.scalar_one_or_none()

                            if match_id:
                                await session.execute(
                                    text("""
                                        INSERT INTO text_relations
                                            (text_a_id, text_b_id, relation_type, source, confidence)
                                        VALUES (:a, :b, 'parallel', 'suttacentral', 0.8)
                                        ON CONFLICT ON CONSTRAINT uq_text_relation DO NOTHING
                                    """),
                                    {"a": bt.id, "b": match_id},
                                )
                                await session.commit()
                                self.stats.relations_created += 1

            except Exception as e:
                if "404" not in str(e):
                    self.stats.errors += 1

            if (i + 1) % 200 == 0:
                print(f"  Parallels: {i + 1}/{len(sc_texts)}, "
                      f"relations={self.stats.relations_created}")

        print(f"  Phase C done: {self.stats.relations_created} parallel relations.")

    async def run_import(self):
        if self.parallels_only:
            await self.phase_c_parallels()
        elif self.content_only:
            await self.phase_b_content()
        else:
            await self.phase_a_catalog()
            await self.phase_b_content()
            await self.phase_c_parallels()


async def main():
    parser = argparse.ArgumentParser(description="Import SuttaCentral Pali canon")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of texts")
    parser.add_argument("--content-only", action="store_true", help="Only fetch content (skip catalog)")
    parser.add_argument("--parallels-only", action="store_true", help="Only create parallel relations")
    args = parser.parse_args()

    importer = SuttaCentralImporter(
        limit=args.limit,
        content_only=args.content_only,
        parallels_only=args.parallels_only,
    )
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
