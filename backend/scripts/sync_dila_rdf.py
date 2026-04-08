"""Sync DILA persons from GitHub RDF dump.

Downloads the latest person.rdf from DILA-edu/lod repo,
parses it, and upserts into kg_entities.
Fast: ~1 minute for full sync vs 6 hours for API crawl.
"""
import asyncio
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.config import settings

RDF_URL = "https://raw.githubusercontent.com/DILA-edu/lod/master/rdf/person.rdf"
LOCAL_PATH = "/tmp/dila_person.rdf"


def download_rdf():
    print("Downloading DILA person.rdf from GitHub...")
    req = urllib.request.Request(RDF_URL, headers={"User-Agent": "FoJinBot/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    with open(LOCAL_PATH, "wb") as f:
        f.write(data)
    print(f"  Downloaded {len(data) / 1024 / 1024:.1f} MB")


def parse_rdf():
    print("Parsing RDF...")
    with open(LOCAL_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = re.findall(
        r'<rdf:Description rdf:about="http://purl\.dila\.edu\.tw/resource/(A\d+)">(.*?)</rdf:Description>',
        content, re.DOTALL
    )

    persons = {}
    for aid, block in blocks:
        name_zh = ""
        for lang in ["zh-Hant", "zh"]:
            m = re.search(rf'<skos:prefLabel xml:lang="{lang}">(.+?)</skos:prefLabel>', block)
            if m:
                name_zh = m.group(1).strip()
                break
        if not name_zh:
            continue

        name_en = ""
        for lang in ["sa-x-iast", "en", "pi-x-iast"]:
            m = re.search(rf'<skos:prefLabel xml:lang="{lang}">(.+?)</skos:prefLabel>', block)
            if m:
                name_en = m.group(1).strip()
                break

        desc = ""
        m = re.search(r'<bdo:noteText>(.+?)</bdo:noteText>', block, re.DOTALL)
        if m:
            desc = re.sub(r'<[^>]+>', '', m.group(1)).strip()

        birth_year = death_year = None
        m = re.search(r'PersonBirth.*?onYear[^>]*>([+-]?\d+)<', block, re.DOTALL)
        if m:
            birth_year = m.group(1).lstrip("+").lstrip("0") or None
        m = re.search(r'PersonDeath.*?onYear[^>]*>([+-]?\d+)<', block, re.DOTALL)
        if m:
            death_year = m.group(1).lstrip("+").lstrip("0") or None
        if not death_year:
            m = re.search(r'PersonDeath.*?notBefore[^>]*>([+-]?\d{4})', block, re.DOTALL)
            if m:
                death_year = m.group(1).lstrip("+").lstrip("0") or None

        gender = None
        if "GenderMale" in block:
            gender = "male"
        elif "GenderFemale" in block:
            gender = "female"

        persons[aid] = {
            "aid": aid, "name_zh": name_zh, "name_en": name_en,
            "desc": desc, "birth_year": birth_year, "death_year": death_year,
            "gender": gender,
        }

    print(f"  Parsed {len(persons)} persons")
    return persons


async def sync_to_db(persons: dict):
    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sf() as session:
        # Get existing DILA IDs
        result = await session.execute(text(
            "SELECT external_ids->>'dila' FROM kg_entities "
            "WHERE entity_type='person' AND external_ids->>'dila' IS NOT NULL"
        ))
        existing = {r[0] for r in result.fetchall()}
        print(f"  Existing in DB: {len(existing)}")

        new_persons = {k: v for k, v in persons.items() if k not in existing}
        print(f"  New to import: {len(new_persons)}")

        if not new_persons:
            print("  Already up to date!")
            await engine.dispose()
            return 0

        # Batch insert
        inserted = 0
        items = list(new_persons.values())
        for i in range(0, len(items), 200):
            batch = items[i:i+200]
            for p in batch:
                props = {"source": "dila"}
                if p["birth_year"]:
                    props["birth_year"] = p["birth_year"]
                if p["death_year"]:
                    props["death_year"] = p["death_year"]
                if p["gender"]:
                    props["gender"] = p["gender"]

                await session.execute(text("""
                    INSERT INTO kg_entities (entity_type, name_zh, name_en, description, properties, external_ids)
                    VALUES ('person', :name_zh, :name_en, :desc, :props::json, :ext::json)
                """), {
                    "name_zh": p["name_zh"],
                    "name_en": p["name_en"] or "",
                    "desc": p["desc"] or "",
                    "props": json.dumps(props, ensure_ascii=False),
                    "ext": json.dumps({"dila": p["aid"]}),
                })
                inserted += 1

            await session.commit()
            print(f"  [{inserted}/{len(new_persons)}] committed")

        print(f"\n{'='*60}")
        print(f"Sync complete: {inserted} new persons imported")
        print(f"{'='*60}")
        await engine.dispose()
        return inserted


async def main():
    download_rdf()
    persons = parse_rdf()
    await sync_to_db(persons)


if __name__ == "__main__":
    asyncio.run(main())
