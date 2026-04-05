"""Further audit: check Wikidata P31 (instance of) for entities with coords.
Fetch P31 types from Wikidata and flag any that aren't Buddhist-related.
"""
import asyncio, json, os, sys, time
import urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings

# Wikidata classes that ARE Buddhist-related
BUDDHIST_CLASSES = {
    "Q5393308",   # Buddhist temple
    "Q160742",    # monastery (generic but includes Buddhist)
    "Q178561",    # stupa
    "Q1030034",   # cave temple
    "Q56242071",  # Chan temple
    "Q2977",      # cathedral (not Buddhist but generic religious)
    "Q24398318",  # religious building
    "Q2633349",   # place of worship
    "Q839954",    # archaeological site
    "Q23413",     # castle (some Japanese temples)
    "Q44613",     # monastery
    "Q108325",    # temple
    "Q2048319",   # Shinto shrine (Japan — related)
    "Q1068383",   # pagoda
    "Q15661340",  # ancient monastery
    "Q107026",    # pilgrimage site
    "Q570116",    # tourist attraction
    "Q1050544",   # historic building
    "Q47848",     # chapel
    "Q2526135",   # protected area
    "Q35509",     # cave
    "Q1183543",   # building complex
    "Q7318926",   # religious order
    "Q820477",    # mine (false positive)
    "Q1021645",   # religious site
    "Q19953632",  # former religious building
    "Q29023235",  # dergyis monastery / dgon pa
}

# Classes that are DEFINITELY NOT Buddhist
NON_BUDDHIST_CLASSES = {
    "Q33506",     # museum
    "Q207694",    # art museum
    "Q43229",     # organization
    "Q5003624",   # memorial
    "Q19953641",  # Roman Catholic church
    "Q43501",     # zoo
    "Q22746",     # urban park
    "Q22698",     # park
    "Q167346",    # botanical garden
    "Q16917",     # hospital
    "Q3914",      # school
    "Q3918",      # university
    "Q41176",     # building
    "Q7075",      # library
    "Q131734",    # brewery
    "Q10387685",  # distillery
    "Q2416723",   # winery
    "Q11396556",  # memorial hall
    "Q697295",    # tomb
    "Q39614",     # cemetery
    "Q132834",    # tram museum
    "Q11424",     # film
    "Q4830453",   # business
    "Q7075",      # library
    "Q14659",     # stadium
    "Q1248784",   # airport
    "Q28640",     # profession
    "Q178706",    # palace
    "Q23413",     # castle
    "Q1307579",   # shopping center
    "Q27686",     # hotel
}

USER_AGENT = "FoJinBot/1.0"

def batch_query(qids: list[str]) -> dict[str, list[str]]:
    """Query Wikidata for P31 of multiple entities. Returns {qid: [type_qids]}."""
    values = " ".join(f"wd:{q}" for q in qids)
    sparql = f"""
    SELECT ?item ?type WHERE {{
      VALUES ?item {{ {values} }}
      ?item wdt:P31 ?type .
    }}
    """
    params = urllib.parse.urlencode({"query": sparql, "format": "json"})
    url = f"https://query.wikidata.org/sparql?{params}"
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/sparql-results+json",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())

    result = {}
    for b in data.get("results", {}).get("bindings", []):
        item = b["item"]["value"].split("/")[-1]
        typ = b["type"]["value"].split("/")[-1]
        result.setdefault(item, []).append(typ)
    return result


async def main():
    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        # Get wikidata IDs of entities with coords and wikidata source
        r = await s.execute(text("""
            SELECT id, name_zh, name_en, entity_type, external_ids->>'wikidata' as wid
            FROM kg_entities
            WHERE (properties->>'latitude') IS NOT NULL
              AND external_ids->>'wikidata' IS NOT NULL
              AND (properties->>'geo_source' LIKE 'wikidata:%' OR properties->>'geo_source' = 'bdrc')
        """))
        rows = r.fetchall()
        print(f"Auditing {len(rows)} entities with Wikidata IDs...")

        to_delete = []
        buddhist_kept = 0
        unknown = 0

        # Batch queries 50 at a time
        for i in range(0, len(rows), 50):
            batch = rows[i:i+50]
            qids = [row[4] for row in batch]
            try:
                types = batch_query(qids)
            except Exception as e:
                print(f"  SPARQL error: {e}, sleeping 10s")
                time.sleep(10)
                continue

            for eid, name_zh, name_en, etype, wid in batch:
                entity_types = types.get(wid, [])
                if not entity_types:
                    unknown += 1
                    continue

                has_buddhist = any(t in BUDDHIST_CLASSES for t in entity_types)
                has_non_buddhist = any(t in NON_BUDDHIST_CLASSES for t in entity_types)

                # Only flag if CLEARLY non-Buddhist (in NON list, not in Buddhist list)
                if has_non_buddhist and not has_buddhist:
                    to_delete.append((eid, name_zh, name_en, entity_types))

            if i % 500 == 0:
                print(f"  ... audited {i}/{len(rows)}, flagged {len(to_delete)}")
            time.sleep(1)  # Rate limit

        print(f"\n=== Flagged {len(to_delete)} entities as non-Buddhist ===")
        for eid, zh, en, types in to_delete[:30]:
            print(f"  #{eid} '{zh}' | {en} | types={types}")
        if len(to_delete) > 30:
            print(f"  ... and {len(to_delete) - 30} more")

        # Save for review
        with open("/tmp/flagged_entities.json", "w") as f:
            json.dump([{"id": eid, "name_zh": zh, "name_en": en, "types": types}
                       for eid, zh, en, types in to_delete], f, ensure_ascii=False, indent=2)
        print(f"\nFlagged list saved to /tmp/flagged_entities.json")
        print(f"Unknown (no P31 found): {unknown}")

    await engine.dispose()

asyncio.run(main())
