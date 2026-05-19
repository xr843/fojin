"""
Import VRI (Vipassana Research Institute) Tipitaka — Chaṭṭha Saṅgāyana edition.

The Chaṭṭha Saṅgāyana (6th Buddhist Council) Pali Tipitaka is the Burmese
recension of the Pali canon, published electronically by VRI.

Usage:
    python scripts/import_vri_tipitaka.py
    python scripts/import_vri_tipitaka.py --limit 50
    python scripts/import_vri_tipitaka.py --local-dir data/vri
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

from app.core.elasticsearch import INDEX_NAME
from app.models.text import BuddhistText


VRI_BASE = "https://tipitaka.org"


class VRITipitakaImporter(BaseImporter):
    SOURCE_CODE = "vri"
    SOURCE_NAME_ZH = "VRI 巴利三藏"
    SOURCE_NAME_EN = "Vipassana Research Institute Tipitaka"
    SOURCE_BASE_URL = VRI_BASE
    SOURCE_DESCRIPTION = "内观研究院发布的第六次结集巴利三藏，缅甸传统版本"
    RATE_LIMIT_DELAY = 2.0

    def __init__(self, limit: int = 0, local_dir: str | None = None):
        super().__init__()
        self.limit = limit
        self.local_dir = local_dir

    # VRI Tipitaka divisions mapping
    VRI_DIVISIONS = [
        # Vinaya Piṭaka
        {"id": "vin-par", "title_pi": "Pārājika", "title_en": "Pārājika (Vinaya)", "division": "Vinaya"},
        {"id": "vin-pac", "title_pi": "Pācittiya", "title_en": "Pācittiya (Vinaya)", "division": "Vinaya"},
        {"id": "vin-mv", "title_pi": "Mahāvagga", "title_en": "Mahāvagga (Vinaya)", "division": "Vinaya"},
        {"id": "vin-cv", "title_pi": "Cūḷavagga", "title_en": "Cūḷavagga (Vinaya)", "division": "Vinaya"},
        {"id": "vin-pvr", "title_pi": "Parivāra", "title_en": "Parivāra (Vinaya)", "division": "Vinaya"},
        # Sutta Piṭaka — Dīgha Nikāya
        {"id": "dn-silakkhandha", "title_pi": "Sīlakkhandhavagga", "title_en": "Division on Morality (DN 1-13)", "division": "Sutta"},
        {"id": "dn-maha", "title_pi": "Mahāvagga", "title_en": "Great Division (DN 14-23)", "division": "Sutta"},
        {"id": "dn-patika", "title_pi": "Pāṭikavagga", "title_en": "Pāṭika Division (DN 24-34)", "division": "Sutta"},
        # Sutta Piṭaka — Majjhima Nikāya
        {"id": "mn-mulapannasa", "title_pi": "Mūlapaṇṇāsa", "title_en": "Root Fifty (MN 1-50)", "division": "Sutta"},
        {"id": "mn-majjhimapannasa", "title_pi": "Majjhimapaṇṇāsa", "title_en": "Middle Fifty (MN 51-100)", "division": "Sutta"},
        {"id": "mn-uparipannasa", "title_pi": "Uparipaṇṇāsa", "title_en": "Final Fifty (MN 101-152)", "division": "Sutta"},
        # Sutta Piṭaka — Saṃyutta Nikāya
        {"id": "sn-sagatha", "title_pi": "Sagāthāvagga", "title_en": "Connected Discourses with Verses (SN 1-11)", "division": "Sutta"},
        {"id": "sn-nidana", "title_pi": "Nidānavagga", "title_en": "Connected Discourses on Causation (SN 12-21)", "division": "Sutta"},
        {"id": "sn-khandha", "title_pi": "Khandhavagga", "title_en": "Connected Discourses on the Aggregates (SN 22-34)", "division": "Sutta"},
        {"id": "sn-salayatana", "title_pi": "Saḷāyatanavagga", "title_en": "Connected Discourses on the Six Sense Bases (SN 35-44)", "division": "Sutta"},
        {"id": "sn-maha", "title_pi": "Mahāvagga", "title_en": "Great Book (SN 45-56)", "division": "Sutta"},
        # Sutta Piṭaka — Aṅguttara Nikāya
        {"id": "an-ekaka", "title_pi": "Ekakanipāta", "title_en": "Book of the Ones (AN 1)", "division": "Sutta"},
        {"id": "an-duka", "title_pi": "Dukanipāta", "title_en": "Book of the Twos (AN 2)", "division": "Sutta"},
        {"id": "an-tika", "title_pi": "Tikanipāta", "title_en": "Book of the Threes (AN 3)", "division": "Sutta"},
        # Sutta Piṭaka — Khuddaka Nikāya
        {"id": "kn-dhp", "title_pi": "Dhammapada", "title_en": "Dhammapada", "division": "Sutta"},
        {"id": "kn-snp", "title_pi": "Sutta Nipāta", "title_en": "Sutta Nipāta", "division": "Sutta"},
        {"id": "kn-thag", "title_pi": "Theragāthā", "title_en": "Verses of the Elder Monks", "division": "Sutta"},
        {"id": "kn-thig", "title_pi": "Therīgāthā", "title_en": "Verses of the Elder Nuns", "division": "Sutta"},
        {"id": "kn-ja", "title_pi": "Jātaka", "title_en": "Birth Stories", "division": "Sutta"},
        # Abhidhamma Piṭaka
        {"id": "abh-dhs", "title_pi": "Dhammasaṅgaṇī", "title_en": "Enumeration of Phenomena", "division": "Abhidhamma"},
        {"id": "abh-vbh", "title_pi": "Vibhaṅga", "title_en": "Book of Analysis", "division": "Abhidhamma"},
        {"id": "abh-dhk", "title_pi": "Dhātukathā", "title_en": "Discourse on Elements", "division": "Abhidhamma"},
        {"id": "abh-pp", "title_pi": "Puggalapaññatti", "title_en": "Description of Individuals", "division": "Abhidhamma"},
        {"id": "abh-kv", "title_pi": "Kathāvatthu", "title_en": "Points of Controversy", "division": "Abhidhamma"},
        {"id": "abh-yam", "title_pi": "Yamaka", "title_en": "Book of Pairs", "division": "Abhidhamma"},
        {"id": "abh-pat", "title_pi": "Paṭṭhāna", "title_en": "Book of Conditional Relations", "division": "Abhidhamma"},
    ]

    async def run_import(self):
        divisions = self.VRI_DIVISIONS

        if self.limit > 0:
            divisions = divisions[:self.limit]

        print(f"\n  Importing {len(divisions)} VRI Tipitaka divisions...")

        async with self.session_factory() as session:
            source = await self.ensure_source(session)
            es_actions = []

            for i, div in enumerate(divisions):
                cbeta_id = f"VRI-{div['id']}"
                title_pi = div["title_pi"]
                title_en = div["title_en"]

                try:
                    result = await session.execute(
                        text("""
                            INSERT INTO buddhist_texts
                                (cbeta_id, title_zh, title_pi, title_en, source_id, lang,
                                 category, has_content)
                            VALUES (:cbeta_id, :title_zh, :title_pi, :title_en, :source_id,
                                    'pi', :category, false)
                            ON CONFLICT (cbeta_id) DO UPDATE SET
                                title_pi = COALESCE(EXCLUDED.title_pi, buddhist_texts.title_pi),
                                title_en = COALESCE(EXCLUDED.title_en, buddhist_texts.title_en)
                            RETURNING id
                        """),
                        {
                            "cbeta_id": cbeta_id,
                            "title_zh": title_pi,
                            "title_pi": title_pi,
                            "title_en": title_en,
                            "source_id": source.id,
                            "category": div["division"],
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
                            "uid": div["id"],
                            "url": f"{VRI_BASE}/romn/{div['id']}",
                        },
                    )
                    self.stats.identifiers_created += 1

                    # Try to find SuttaCentral parallel
                    await self._try_sc_parallel(session, text_id, div["id"])

                    es_actions.append({
                        "_index": INDEX_NAME,
                        "_id": str(text_id),
                        "_source": {
                            "id": text_id,
                            "cbeta_id": cbeta_id,
                            "title_zh": title_pi,
                            "title_pi": title_pi,
                            "title_en": title_en,
                            "lang": "pi",
                            "source_code": "vri",
                            "category": div["division"],
                        },
                    })

                except Exception as e:
                    self.stats.errors += 1
                    print(f"  Error: {div['id']}: {e}")

            await session.commit()

        # ES
        if es_actions:

            async def gen():
                for a in es_actions:
                    yield a

            s, _ = await async_bulk(self.es, gen(), raise_on_error=False)
            print(f"  ES: indexed {s} texts")

    async def _try_sc_parallel(self, session, vri_text_id: int, vri_id: str):
        """Try to create parallel with SuttaCentral texts."""
        # Map VRI IDs to SC collection prefixes
        sc_prefix_map = {
            "dn-": "SC-dn",
            "mn-": "SC-mn",
            "sn-": "SC-sn",
            "an-": "SC-an",
            "kn-dhp": "SC-dhp",
            "kn-snp": "SC-snp",
        }

        for prefix, sc_prefix in sc_prefix_map.items():
            if vri_id.startswith(prefix):
                # Find any SC text with matching prefix
                result = await session.execute(
                    select(BuddhistText.id)
                    .where(BuddhistText.cbeta_id.startswith(sc_prefix))
                    .limit(1)
                )
                sc_id = result.scalar_one_or_none()
                if sc_id:
                    await session.execute(
                        text("""
                            INSERT INTO text_relations
                                (text_a_id, text_b_id, relation_type, source, confidence)
                            VALUES (:a, :b, 'parallel', 'vri', 0.7)
                            ON CONFLICT ON CONSTRAINT uq_text_relation DO NOTHING
                        """),
                        {"a": vri_text_id, "b": sc_id},
                    )
                    self.stats.relations_created += 1
                break


async def main():
    parser = argparse.ArgumentParser(description="Import VRI Tipitaka")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of divisions")
    parser.add_argument("--local-dir", type=str, help="Use local directory")
    args = parser.parse_args()

    importer = VRITipitakaImporter(limit=args.limit, local_dir=args.local_dir)
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
