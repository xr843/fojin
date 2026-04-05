"""Audit what languages entities' names are stored in, and description coverage."""
import asyncio, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings

HIRAGANA = re.compile(r'[\u3040-\u309F]')
KATAKANA = re.compile(r'[\u30A0-\u30FF]')
HANGUL = re.compile(r'[\uAC00-\uD7AF\u1100-\u11FF]')
MONGOLIAN = re.compile(r'[\u1800-\u18AF]')
CJK = re.compile(r'[\u4E00-\u9FFF]')
LATIN = re.compile(r'[a-zA-Z]')

def classify_name(name: str) -> str:
    if not name: return "empty"
    if HANGUL.search(name): return "korean_hangul"
    if HIRAGANA.search(name) or KATAKANA.search(name): return "japanese_kana"
    if MONGOLIAN.search(name): return "mongolian"
    has_cjk = bool(CJK.search(name))
    has_latin = bool(LATIN.search(name))
    if has_cjk and not has_latin: return "chinese_kanji"
    if has_cjk and has_latin: return "mixed_cjk_latin"
    if has_latin: return "latin_english"
    return "other"

async def main():
    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        r = await s.execute(text("""
            SELECT entity_type, name_zh, name_en, description
            FROM kg_entities
            WHERE (properties->>'latitude') IS NOT NULL
        """))
        rows = r.fetchall()

        lang_counts: dict[str, int] = {}
        by_type_lang: dict[tuple, int] = {}
        has_description = 0
        has_desc_zh = 0

        for etype, name_zh, name_en, desc in rows:
            cls = classify_name(name_zh)
            lang_counts[cls] = lang_counts.get(cls, 0) + 1
            by_type_lang[(etype, cls)] = by_type_lang.get((etype, cls), 0) + 1
            if desc:
                has_description += 1
                if CJK.search(desc):
                    has_desc_zh += 1

        print(f"Total entities with coords: {len(rows)}\n")
        print("=== name_zh 字段语言分布 ===")
        for lang, cnt in sorted(lang_counts.items(), key=lambda x: -x[1]):
            pct = cnt / len(rows) * 100
            print(f"  {lang}: {cnt} ({pct:.1f}%)")

        print(f"\n=== description 覆盖 ===")
        print(f"有 description: {has_description} ({has_description/len(rows)*100:.1f}%)")
        print(f"其中含中文: {has_desc_zh}")

        print(f"\n=== 按类型+语言分布（非中文）===")
        for (etype, lang), cnt in sorted(by_type_lang.items(), key=lambda x: -x[1]):
            if lang in ("chinese_kanji", "empty"):
                continue
            print(f"  [{etype}] {lang}: {cnt}")

    await engine.dispose()

asyncio.run(main())
