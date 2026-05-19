"""
Import 莊春江讀經站 (Buddhason Agama Reading Station).

Website: https://agama.buddhason.org/

Scrapes comparative Agama–Nikaya texts with Chinese translations, Pali originals,
and scholarly commentary by 莊春江 (Zhuang Chunjiang).

Collections:
  Agamas:  SA (1362), MA (222), DA (30), AA (470)
  Nikayas: SN (~2900), MN (152), DN (34), AN (~1764)

Three phases:
  A. Catalog: scrape index pages to discover all texts
  B. Content: fetch each text page, parse Chinese + Pali content
  C. Parallels: create cross-references between Agama ↔ Nikaya texts

Usage:
    python scripts/import_buddhason.py
    python scripts/import_buddhason.py --limit 50
    python scripts/import_buddhason.py --content-only
    python scripts/import_buddhason.py --parallels-only
    python scripts/import_buddhason.py --collection SA
"""

import argparse
import asyncio
import os
import re
import sys
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.base_importer import BaseImporter

from sqlalchemy import text
from elasticsearch.helpers import async_bulk

from app.core.elasticsearch import INDEX_NAME, CONTENT_INDEX_NAME

BASE_URL = "https://agama.buddhason.org"

# ── Collection definitions ──────────────────────────────────────────────
# (code, name_zh, name_en, type, lang, index_path, link_pattern)
# type: "agama" has div.agama + div.nikaya + div.pali
#       "nikaya" has div.nikaya + div.pali
COLLECTIONS = [
    # 四阿含 (Northern Agamas)
    ("SA", "雜阿含經", "Saṃyukta Āgama", "agama", "lzh",
     "SA/index.htm", r'href="(SA\d+\.htm)"'),
    ("MA", "中阿含經", "Madhyama Āgama", "agama", "lzh",
     "MA/index.htm", r'href="(MA\d+\.htm)"'),
    ("DA", "長阿含經", "Dīrgha Āgama", "agama", "lzh",
     "DA/index.htm", r'href="(DA\d+\.htm)"'),
    ("AA", "增壹阿含經", "Ekottara Āgama", "agama", "lzh",
     "AA/index.htm", r'href="(AA\d+\.htm)"'),
    # 四部 (Pali Nikayas — Chinese translations)
    ("SN", "相應部", "Saṃyutta Nikāya", "nikaya", "pi",
     "SN/index.htm", r'href="(SN\d+\.htm)"'),
    ("MN", "中部", "Majjhima Nikāya", "nikaya", "pi",
     "MN/index.htm", r'href="(MN\d+\.htm)"'),
    ("DN", "長部", "Dīgha Nikāya", "nikaya", "pi",
     "DN/index.htm", r'href="(DN\d+\.htm)"'),
    ("AN", "增支部", "Aṅguttara Nikāya", "nikaya", "pi",
     "AN/index.htm", r'href="(AN\d+\.htm)"'),
]

# Minor texts (Khuddaka) — no index page, use known ranges
MINOR_COLLECTIONS = [
    ("Ud", "自說經", "Udāna", "nikaya", "pi", "Ud/index.htm", r'href="(Ud\d+\.htm)"'),
    ("It", "如是語經", "Itivuttaka", "nikaya", "pi", "It/index.htm", r'href="(It\d+\.htm)"'),
    ("Dh", "法句經", "Dhammapada", "nikaya", "pi", None, None),
    ("Su", "經集", "Sutta Nipāta", "nikaya", "pi", None, None),
    ("Th", "長老偈經", "Theragāthā", "nikaya", "pi", None, None),
    ("Ti", "長老尼偈經", "Therīgāthā", "nikaya", "pi", None, None),
    ("Ja", "本生經", "Jātaka", "nikaya", "pi", None, None),
]


def strip_html(html: str) -> str:
    """Remove HTML tags and clean up whitespace, preserving line breaks."""
    # Replace <br> variants with newlines
    text_content = re.sub(r'<br\s*/?\s*>', '\n', html, flags=re.IGNORECASE)
    # Remove all remaining tags
    text_content = re.sub(r'<[^>]+>', '', text_content)
    # Clean up: decode entities
    text_content = text_content.replace('&nbsp;', ' ').replace('&amp;', '&')
    text_content = text_content.replace('&lt;', '<').replace('&gt;', '>')
    # Remove leading whitespace chars (fullwidth and halfwidth spaces)
    text_content = re.sub(r'^[\u3000\s]+', '', text_content, flags=re.MULTILINE)
    # Collapse multiple blank lines
    text_content = re.sub(r'\n{3,}', '\n\n', text_content)
    return text_content.strip()


def parse_sutra_page(html: str, collection_type: str) -> dict:
    """
    Parse a Buddhason sutra page and extract structured content.

    Returns dict with keys:
        title: str — page title
        agama_ref: str — Northern transmission reference (agama pages only)
        nikaya_ref: str — Southern transmission reference
        subject: str — thematic keywords
        chinese_text: str — main Chinese text (agama or nikaya translation)
        pali_text: str — Pali original text
        commentary: str — comparative notes
        parallel_refs: list[str] — cross-reference codes found in text
    """
    result = {
        "title": "",
        "agama_ref": "",
        "nikaya_ref": "",
        "subject": "",
        "chinese_text": "",
        "pali_text": "",
        "commentary": "",
        "parallel_refs": [],
    }

    # Title from <title> tag
    title_match = re.search(r'<title>([^<]+)</title>', html)
    if title_match:
        result["title"] = title_match.group(1).strip()

    # Cross-references from #north div
    agama_ref = re.search(r'class="agama">北傳:([^<]+)<', html)
    if agama_ref:
        result["agama_ref"] = agama_ref.group(1).strip()

    nikaya_ref = re.search(r'class="nikaya">南傳:([^<]+)<', html)
    if nikaya_ref:
        result["nikaya_ref"] = nikaya_ref.group(1).strip()

    # Subject/theme
    subject_match = re.search(r'class="subject">([^<]+)<', html)
    if subject_match:
        result["subject"] = subject_match.group(1).strip()

    # Extract div contents using regex (pages are simple enough)
    # Chinese text: div.agama (for agama pages) or div.nikaya (for nikaya pages)
    chinese_parts = []

    if collection_type == "agama":
        # Agama pages have both div.agama (Northern) and div.nikaya (Southern translation)
        agama_div = re.search(
            r'<div\s+class="agama">(.*?)</div>', html, re.DOTALL
        )
        if agama_div:
            chinese_parts.append(strip_html(agama_div.group(1)))

        nikaya_div = re.search(
            r'<div\s+class="nikaya">(.*?)</div>', html, re.DOTALL
        )
        if nikaya_div:
            chinese_parts.append(strip_html(nikaya_div.group(1)))
    else:
        # Nikaya pages have div.nikaya only
        nikaya_div = re.search(
            r'<div\s+class="nikaya">(.*?)</div>', html, re.DOTALL
        )
        if nikaya_div:
            chinese_parts.append(strip_html(nikaya_div.group(1)))

    result["chinese_text"] = "\n\n".join(p for p in chinese_parts if p)

    # Pali text: div.pali
    pali_div = re.search(r'<div\s+class="pali">(.*?)</div>', html, re.DOTALL)
    if pali_div:
        result["pali_text"] = strip_html(pali_div.group(1))

    # Commentary: div.comp
    comp_div = re.search(r'<div\s+class="comp">(.*?)</div>', html, re.DOTALL)
    if comp_div:
        result["commentary"] = strip_html(comp_div.group(1))

    # Extract parallel references like [SA.1267] or (SA.1267)
    # Only match clean refs: collection code + dot + digits (optional range)
    parallel_refs = re.findall(
        r'[\[\(]((?:SA|MA|DA|AA|SN|MN|DN|AN)\.\d+(?:[-.]\d+)?)\s*[\]\)]', html
    )
    result["parallel_refs"] = list(set(parallel_refs))

    return result


class BuddhaSONImporter(BaseImporter):
    SOURCE_CODE = "buddhason"
    SOURCE_NAME_ZH = "莊春江讀經站"
    SOURCE_NAME_EN = "Zhuang Chunjiang Agama Reading Station"
    SOURCE_BASE_URL = BASE_URL
    SOURCE_DESCRIPTION = (
        "阿含经南北传对读平台，提供四阿含与四部的汉译对照、巴利原文及比对注释"
    )
    RATE_LIMIT_DELAY = 0.5  # Be polite to a personal site

    def __init__(self, limit: int = 0, content_only: bool = False,
                 parallels_only: bool = False, collection: str | None = None):
        super().__init__()
        self.limit = limit
        self.content_only = content_only
        self.parallels_only = parallels_only
        self.collection_filter = collection.upper() if collection else None

    def _get_collections(self) -> list[tuple]:
        """Return filtered collection list."""
        collections = COLLECTIONS
        if self.collection_filter:
            collections = [c for c in collections if c[0] == self.collection_filter]
            if not collections:
                # Try minor collections
                minor = [c for c in MINOR_COLLECTIONS
                         if c[0] == self.collection_filter and c[5] is not None]
                collections = minor
        return collections

    async def _discover_index(self, index_url: str, link_pattern: str) -> list[str]:
        """Scrape an index page and return list of .htm filenames."""
        resp = await self.rate_limited_get(index_url)
        html = resp.text
        filenames = re.findall(link_pattern, html)
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for f in filenames:
            if f not in seen:
                seen.add(f)
                unique.append(f)
        return unique

    async def phase_a_catalog(self):
        """Phase A: Discover all texts from index pages and create catalog entries."""
        print("\n[Phase A] Discovering Buddhason catalog...")

        checkpoint = self.load_checkpoint()
        if checkpoint.get("phase_a_done"):
            print("  Phase A already completed (checkpoint). Skipping.")
            return

        collections = self._get_collections()
        total_discovered = 0

        for coll_code, name_zh, name_en, coll_type, lang, index_path, link_pattern in collections:
            if index_path is None:
                continue

            index_url = f"{BASE_URL}/{index_path}"
            print(f"\n  Discovering {coll_code} ({name_zh})...")

            try:
                filenames = await self._discover_index(index_url, link_pattern)
            except Exception as e:
                print(f"    Error fetching index: {e}")
                self.stats.errors += 1
                continue

            if self.limit > 0:
                filenames = filenames[:self.limit]

            print(f"    Found {len(filenames)} texts")

            async with self.session_factory() as session:
                source = await self.ensure_source(session)
                es_actions = []

                for i, filename in enumerate(filenames):
                    # Extract number: SA0001.htm → 0001, MA001.htm → 001
                    num_match = re.search(r'(\d+)', filename)
                    num = num_match.group(1) if num_match else filename.replace('.htm', '')

                    cbeta_id = f"BS-{coll_code}{num}"
                    title = f"{name_zh}第{int(num)}經"
                    source_url = f"{BASE_URL}/{coll_code}/{filename}"

                    result = await session.execute(
                        text("""
                            INSERT INTO buddhist_texts
                                (cbeta_id, title_zh, title_en, source_id, lang, has_content,
                                 category)
                            VALUES (:cbeta_id, :title_zh, :title_en, :source_id, :lang, false,
                                    :category)
                            ON CONFLICT (cbeta_id) DO UPDATE SET
                                title_zh = EXCLUDED.title_zh,
                                title_en = COALESCE(EXCLUDED.title_en, buddhist_texts.title_en)
                            RETURNING id
                        """),
                        {
                            "cbeta_id": cbeta_id,
                            "title_zh": title,
                            "title_en": f"{name_en} {int(num)}",
                            "source_id": source.id,
                            "lang": lang,
                            "category": "阿含部" if coll_type == "agama" else "巴利藏",
                        },
                    )
                    text_id = result.scalar_one()

                    # TextIdentifier
                    await session.execute(
                        text("""
                            INSERT INTO text_identifiers
                                (text_id, source_id, source_uid, source_url)
                            VALUES (:text_id, :source_id, :uid, :url)
                            ON CONFLICT ON CONSTRAINT uq_text_identifier_source_uid DO NOTHING
                        """),
                        {
                            "text_id": text_id,
                            "source_id": source.id,
                            "uid": f"{coll_code}-{num}",
                            "url": source_url,
                        },
                    )

                    es_actions.append({
                        "_index": INDEX_NAME,
                        "_id": str(text_id),
                        "_source": {
                            "id": text_id,
                            "cbeta_id": cbeta_id,
                            "title_zh": title,
                            "title_en": f"{name_en} {int(num)}",
                            "lang": lang,
                            "source_code": "buddhason",
                            "category": "阿含部" if coll_type == "agama" else "巴利藏",
                        },
                    })

                    self.stats.texts_created += 1

                    if (i + 1) % 500 == 0:
                        await session.flush()
                        print(f"    {coll_code}: {i + 1}/{len(filenames)} processed...")

                await session.commit()

            # Bulk ES index
            if es_actions:
                async def gen(actions=es_actions):
                    for a in actions:
                        yield a

                success, _ = await async_bulk(self.es, gen(), raise_on_error=False)
                print(f"    ES indexed: {success}")

            total_discovered += len(filenames)

        self.save_checkpoint({"phase_a_done": True})
        print(f"\n  Phase A done: {total_discovered} texts catalogued "
              f"({self.stats.texts_created} created)")

    async def phase_b_content(self):
        """Phase B: Fetch and parse content for each text."""
        print("\n[Phase B] Importing Buddhason content...")

        checkpoint = self.load_checkpoint()
        last_uid = checkpoint.get("phase_b_last_uid")

        async with self.session_factory() as session:
            source = await self.ensure_source(session)

            from sqlalchemy import select
            from app.models.text import BuddhistText
            from app.models.source import TextIdentifier

            # Get all texts with their source URLs
            result = await session.execute(
                select(BuddhistText, TextIdentifier.source_url, TextIdentifier.source_uid)
                .join(TextIdentifier, TextIdentifier.text_id == BuddhistText.id)
                .where(TextIdentifier.source_id == source.id)
                .order_by(BuddhistText.cbeta_id)
            )
            all_rows = list(result.all())

        # Resume support
        if last_uid:
            skip = True
            filtered = []
            for row in all_rows:
                uid = row[2]  # source_uid
                if skip:
                    if uid == last_uid:
                        skip = False
                    continue
                filtered.append(row)
            all_rows = filtered
            print(f"  Resuming after {last_uid}, {len(all_rows)} remaining.")

        if self.limit > 0:
            all_rows = all_rows[:self.limit]

        # Filter by collection if specified
        if self.collection_filter:
            all_rows = [r for r in all_rows
                        if r[2].startswith(self.collection_filter + "-")]

        print(f"  Processing {len(all_rows)} texts for content...")

        for i, (bt, source_url, source_uid) in enumerate(all_rows):
            coll_code = source_uid.split("-")[0]

            # Determine collection type
            coll_type = "agama"
            for c in COLLECTIONS:
                if c[0] == coll_code:
                    coll_type = c[3]
                    break

            try:
                resp = await self.rate_limited_get(source_url)
                html = resp.text
                parsed = parse_sutra_page(html, coll_type)

                # Update title with actual title from page
                if parsed["title"]:
                    actual_title = parsed["title"]
                else:
                    actual_title = bt.title_zh

                # Get sutra name from span.sutra_name (first one)
                sutra_names = re.findall(
                    r'class="sutra_name">([^<]+)</span>', html
                )
                if sutra_names:
                    actual_title = sutra_names[0].strip()
                    # Remove translator info in parentheses at the end
                    actual_title = re.sub(r'\(.*?莊春江.*?\)\s*$', '', actual_title).strip()

                async with self.session_factory() as session:
                    # Update title
                    await session.execute(
                        text("""
                            UPDATE buddhist_texts
                            SET title_zh = :title_zh
                            WHERE id = :id AND title_zh LIKE :pattern
                        """),
                        {
                            "id": bt.id,
                            "title_zh": actual_title,
                            "pattern": "%第%經",  # Only update generic titles
                        },
                    )

                    # Store Chinese text content
                    chinese = parsed["chinese_text"]
                    if chinese:
                        lang = "lzh" if coll_type == "agama" else "zh"
                        await session.execute(
                            text("""
                                INSERT INTO text_contents
                                    (text_id, juan_num, content, char_count, lang)
                                VALUES (:text_id, 1, :content, :char_count, :lang)
                                ON CONFLICT ON CONSTRAINT uq_text_content_text_juan_lang
                                DO UPDATE SET
                                    content = EXCLUDED.content,
                                    char_count = EXCLUDED.char_count
                            """),
                            {
                                "text_id": bt.id,
                                "content": chinese,
                                "char_count": len(chinese),
                                "lang": lang,
                            },
                        )
                        self.stats.contents_created += 1

                        # ES index for Chinese content
                        await self.es.index(
                            index=CONTENT_INDEX_NAME,
                            id=f"{bt.id}_1_{lang}",
                            document={
                                "text_id": bt.id,
                                "cbeta_id": bt.cbeta_id,
                                "title_zh": actual_title,
                                "juan_num": 1,
                                "content": chinese[:50000],
                                "char_count": len(chinese),
                                "lang": lang,
                                "source_code": "buddhason",
                            },
                        )

                    # Store Pali text content
                    pali = parsed["pali_text"]
                    if pali:
                        await session.execute(
                            text("""
                                INSERT INTO text_contents
                                    (text_id, juan_num, content, char_count, lang)
                                VALUES (:text_id, 1, :content, :char_count, 'pi')
                                ON CONFLICT ON CONSTRAINT uq_text_content_text_juan_lang
                                DO UPDATE SET
                                    content = EXCLUDED.content,
                                    char_count = EXCLUDED.char_count
                            """),
                            {
                                "text_id": bt.id,
                                "content": pali,
                                "char_count": len(pali),
                            },
                        )
                        self.stats.contents_created += 1

                    # Update has_content and char_count
                    total_chars = len(chinese) + len(pali)
                    if total_chars > 0:
                        await session.execute(
                            text("""
                                UPDATE buddhist_texts
                                SET has_content = true,
                                    content_char_count = :cc
                                WHERE id = :id
                            """),
                            {"id": bt.id, "cc": total_chars},
                        )

                    await session.commit()

            except Exception as e:
                self.stats.errors += 1
                if "404" in str(e) or "Not Found" in str(e):
                    self.stats.skipped += 1
                else:
                    print(f"    Error for {source_uid}: {e}")

            if (i + 1) % 100 == 0:
                self.save_checkpoint({
                    "phase_a_done": True,
                    "phase_b_last_uid": source_uid,
                })
                print(f"  Content: {i + 1}/{len(all_rows)}, "
                      f"contents={self.stats.contents_created}, "
                      f"errors={self.stats.errors}")

        self.save_checkpoint({"phase_a_done": True, "phase_b_done": True})
        print(f"  Phase B done: {self.stats.contents_created} contents created.")

    async def phase_c_parallels(self):
        """Phase C: Create parallel relations between Agama and Nikaya texts."""
        print("\n[Phase C] Creating Buddhason parallel relations...")

        # Mapping from Buddhason reference format to cbeta_id prefix
        # e.g., "SA.1267" → look for "BS-SA1267" or cross-ref to CBETA "T0099"
        async with self.session_factory() as session:
            source = await self.ensure_source(session)

            from sqlalchemy import select
            from app.models.text import BuddhistText
            from app.models.source import TextIdentifier

            # Get all Agama texts (they have nikaya_ref cross-references)
            result = await session.execute(
                select(BuddhistText, TextIdentifier.source_url, TextIdentifier.source_uid)
                .join(TextIdentifier, TextIdentifier.text_id == BuddhistText.id)
                .where(TextIdentifier.source_id == source.id)
                .where(BuddhistText.cbeta_id.like("BS-SA%")
                       | BuddhistText.cbeta_id.like("BS-MA%")
                       | BuddhistText.cbeta_id.like("BS-DA%")
                       | BuddhistText.cbeta_id.like("BS-AA%"))
                .order_by(BuddhistText.cbeta_id)
            )
            agama_rows = list(result.all())

        if self.limit > 0:
            agama_rows = agama_rows[:self.limit]

        print(f"  Checking parallels for {len(agama_rows)} Agama texts...")

        for i, (bt, source_url, source_uid) in enumerate(agama_rows):
            try:
                resp = await self.rate_limited_get(source_url)
                html = resp.text

                # Extract nikaya cross-reference from the header
                nikaya_ref_match = re.search(
                    r'class="nikaya">南傳:([^<]+)<', html
                )
                if not nikaya_ref_match:
                    continue

                nikaya_ref = nikaya_ref_match.group(1).strip()

                # Parse references like "相應部22相應12-14經, 相應部22相應51經"
                # Also look for [SA.1267] style inline refs
                inline_refs = re.findall(
                    r'\[((?:SA|MA|DA|AA|SN|MN|DN|AN)[\.\d]+)\]', html
                )

                # For now, create relations with other Buddhason texts
                # Match patterns like SN0012, MN001, etc.
                for ref in inline_refs:
                    # Parse ref: "SA.1267" → coll=SA, num=1267
                    ref_match = re.match(r'(SA|MA|DA|AA|SN|MN|DN|AN)\.(\d+)', ref)
                    if not ref_match:
                        continue
                    ref_coll = ref_match.group(1)
                    ref_num = ref_match.group(2)
                    ref_cbeta_id = f"BS-{ref_coll}{ref_num.zfill(4)}"

                    async with self.session_factory() as session:
                        from app.models.text import BuddhistText as BT
                        result = await session.execute(
                            select(BT.id).where(BT.cbeta_id == ref_cbeta_id)
                        )
                        match_id = result.scalar_one_or_none()

                        if match_id and match_id != bt.id:
                            await session.execute(
                                text("""
                                    INSERT INTO text_relations
                                        (text_a_id, text_b_id, relation_type,
                                         source, confidence)
                                    VALUES (:a, :b, 'parallel', 'buddhason', 0.9)
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
                print(f"  Parallels: {i + 1}/{len(agama_rows)}, "
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
    parser = argparse.ArgumentParser(
        description="Import 莊春江讀經站 (Buddhason Agama Reading Station)"
    )
    parser.add_argument("--limit", type=int, default=0,
                        help="Limit number of texts per collection")
    parser.add_argument("--content-only", action="store_true",
                        help="Only fetch content (skip catalog)")
    parser.add_argument("--parallels-only", action="store_true",
                        help="Only create parallel relations")
    parser.add_argument("--collection", type=str, default=None,
                        help="Import only a specific collection (SA/MA/DA/AA/SN/MN/DN/AN)")
    args = parser.parse_args()

    importer = BuddhaSONImporter(
        limit=args.limit,
        content_only=args.content_only,
        parallels_only=args.parallels_only,
        collection=args.collection,
    )
    await importer.execute()


if __name__ == "__main__":
    asyncio.run(main())
