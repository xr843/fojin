"""Combined DILA sync: RDF bulk + API incremental.

1. Download & import RDF dump (bulk, ~1 min)
2. API scan from max DB ID to latest (incremental, catches RDF lag)

Usage:
    python scripts/sync_dila_combined.py
"""
import asyncio
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.config import settings

RDF_URL = "https://raw.githubusercontent.com/DILA-edu/lod/master/rdf/person.rdf"
DILA_SEARCH = "https://authority.dila.edu.tw/person/search.php"
HEADERS = {"User-Agent": "FoJinBot/1.0 (https://fojin.app)"}


# ── Phase 1: RDF Bulk ──

def download_and_parse_rdf():
    print("=" * 60)
    print("Phase 1: RDF Bulk Import")
    print("=" * 60)
    print("Downloading person.rdf...")
    req = urllib.request.Request(RDF_URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=120) as resp:
        content = resp.read().decode("utf-8")
    print(f"  Downloaded {len(content) / 1024 / 1024:.1f} MB")

    blocks = re.findall(
        r'<rdf:Description rdf:about="http://purl\.dila\.edu\.tw/resource/(A\d+)">(.*?)</rdf:Description>',
        content, re.DOTALL,
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
    print(f"  Parsed {len(persons)} persons from RDF")
    return persons


# ── Phase 2: API Incremental ──

def fetch_dila_page(aid):
    url = f"{DILA_SEARCH}?aid={aid}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def parse_person_html(html, aid):
    # Extract name from <div class='fpr_div'> first heading or title area
    name_zh = ""
    m = re.search(r"<div[^>]*class=['\"]pLabel['\"][^>]*>(.*?)</div>", html, re.DOTALL)
    if m:
        name_zh = re.sub(r'<[^>]+>', '', m.group(1)).strip()
    if not name_zh:
        m = re.search(r'<h2[^>]*>(.*?)</h2>', html, re.DOTALL)
        if m:
            name_zh = re.sub(r'<[^>]+>', '', m.group(1)).strip()
    if not name_zh:
        # Try the first bold text after the aid
        m = re.search(r'<b>(.*?)</b>', html)
        if m:
            name_zh = m.group(1).strip()
    if not name_zh:
        return None

    desc = ""
    m = re.search(r'說明.*?<div[^>]*>(.*?)</div>', html, re.DOTALL)
    if m:
        desc = re.sub(r'<[^>]+>', '', m.group(1)).strip()

    dynasty = ""
    m = re.search(r'朝代.*?<div[^>]*>(.*?)</div>', html, re.DOTALL)
    if m:
        dynasty = re.sub(r'<[^>]+>', '', m.group(1)).strip()

    return {
        "aid": aid, "name_zh": name_zh, "name_en": "",
        "desc": desc, "birth_year": None, "death_year": None,
        "gender": None, "dynasty": dynasty,
    }


def api_incremental_scan(max_db_id):
    print("\n" + "=" * 60)
    print("Phase 2: API Incremental Scan")
    print("=" * 60)
    # Parse numeric part of max ID
    num = int(max_db_id.replace("A", ""))
    empty_streak = 0
    new_persons = {}

    print(f"  Starting from A{num + 1:06d} (DB max: {max_db_id})")

    while empty_streak < 200:
        num += 1
        aid = f"A{num:06d}"
        html = fetch_dila_page(aid)
        time.sleep(0.5)

        if not html or "查無此人" in html or len(html) < 500:
            empty_streak += 1
            continue

        person = parse_person_html(html, aid)
        if person and person["name_zh"]:
            new_persons[aid] = person
            empty_streak = 0
            if len(new_persons) % 20 == 0:
                print(f"  Found {len(new_persons)} new (scanning A{num:06d})")
        else:
            empty_streak += 1

    print(f"  API scan complete: {len(new_persons)} new persons found")
    return new_persons


# ── DB Sync ──

async def sync_to_db(persons: dict):
    engine = create_async_engine(settings.database_url)
    sf = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with sf() as session:
        result = await session.execute(text(
            "SELECT external_ids->>'dila' FROM kg_entities "
            "WHERE entity_type='person' AND external_ids->>'dila' IS NOT NULL"
        ))
        existing = {r[0] for r in result.fetchall()}
        print(f"  Existing in DB: {len(existing)}")

        new = {k: v for k, v in persons.items() if k not in existing}
        print(f"  New to import: {len(new)}")

        if not new:
            print("  Already up to date!")
            await engine.dispose()
            return 0, max(existing) if existing else "A000000"

        inserted = 0
        items = list(new.values())
        for i in range(0, len(items), 200):
            batch = items[i:i + 200]
            for p in batch:
                props = {"source": "dila"}
                if p.get("birth_year"):
                    props["birth_year"] = p["birth_year"]
                if p.get("death_year"):
                    props["death_year"] = p["death_year"]
                if p.get("gender"):
                    props["gender"] = p["gender"]
                await session.execute(text("""
                    INSERT INTO kg_entities (entity_type, name_zh, name_en, description, properties, external_ids)
                    VALUES ('person', :nz, :ne, :desc, :props::json, :ext::json)
                """), {
                    "nz": p["name_zh"], "ne": p.get("name_en", ""),
                    "desc": p.get("desc", ""),
                    "props": json.dumps(props, ensure_ascii=False),
                    "ext": json.dumps({"dila": p["aid"]}),
                })
                inserted += 1
            await session.commit()

        # Get max ID after insert
        result = await session.execute(text(
            "SELECT max(external_ids->>'dila') FROM kg_entities WHERE external_ids->>'dila' IS NOT NULL"
        ))
        max_id = result.scalar() or "A000000"

        print(f"  Inserted {inserted} persons")
        await engine.dispose()
        return inserted, max_id


async def main():
    # Phase 1: RDF bulk
    rdf_persons = download_and_parse_rdf()
    rdf_inserted, max_id = await sync_to_db(rdf_persons)

    # Phase 2: API incremental (catch what RDF missed)
    api_persons = api_incremental_scan(max_id)
    if api_persons:
        api_inserted, _ = await sync_to_db(api_persons)
    else:
        api_inserted = 0

    print("\n" + "=" * 60)
    print(f"Combined sync complete:")
    print(f"  RDF bulk: {rdf_inserted} new")
    print(f"  API incremental: {api_inserted} new")
    print(f"  Total: {rdf_inserted + api_inserted} new persons")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
