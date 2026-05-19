"""Fetch Chinese labels + descriptions from Wikidata for entities with Q-IDs.

Run locally (avoids server IP limits).
Batches 50 Q-IDs per SPARQL query.
"""
import asyncio, json, os, sys, time
import urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

USER_AGENT = "FoJinBot/1.0 (https://fojin.app)"
OUTPUT = "data/wikidata_zh_labels.json"


def batch_query(qids: list[str]) -> dict[str, dict]:
    values = " ".join(f"wd:{q}" for q in qids)
    sparql = f"""
    SELECT ?item ?labelZh ?labelEn ?descZh ?descEn WHERE {{
      VALUES ?item {{ {values} }}
      OPTIONAL {{ ?item rdfs:label ?labelZh FILTER(LANG(?labelZh) IN ("zh", "zh-hans", "zh-cn", "zh-hant", "zh-tw")) }}
      OPTIONAL {{ ?item rdfs:label ?labelEn FILTER(LANG(?labelEn) = "en") }}
      OPTIONAL {{ ?item schema:description ?descZh FILTER(LANG(?descZh) IN ("zh", "zh-hans", "zh-cn", "zh-hant", "zh-tw")) }}
      OPTIONAL {{ ?item schema:description ?descEn FILTER(LANG(?descEn) = "en") }}
    }}
    """
    params = urllib.parse.urlencode({"query": sparql, "format": "json"})
    url = f"https://query.wikidata.org/sparql?{params}"
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/sparql-results+json",
    })
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    result: dict[str, dict] = {}
    for b in data.get("results", {}).get("bindings", []):
        item = b["item"]["value"].split("/")[-1]
        if item not in result:
            result[item] = {}
        for key_sparql, key_py in [("labelZh","label_zh"),("labelEn","label_en"),
                                     ("descZh","desc_zh"),("descEn","desc_en")]:
            val = b.get(key_sparql, {}).get("value", "")
            if val and not result[item].get(key_py):
                result[item][key_py] = val
    return result


async def main():
    # Query DB for all Q-IDs
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from app.config import settings

    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        r = await s.execute(text("""
            SELECT DISTINCT external_ids->>'wikidata'
            FROM kg_entities
            WHERE (properties->>'latitude') IS NOT NULL
              AND external_ids->>'wikidata' IS NOT NULL
        """))
        qids = [row[0] for row in r.fetchall() if row[0]]
    await engine.dispose()

    print(f"Fetching Wikidata labels+descriptions for {len(qids)} Q-IDs...")

    # Load existing if re-running
    existing = {}
    if os.path.exists(OUTPUT):
        with open(OUTPUT) as f:
            existing = json.load(f)
        print(f"Resuming: {len(existing)} already fetched")

    all_results = dict(existing)

    for i in range(0, len(qids), 50):
        batch = [q for q in qids[i:i+50] if q not in all_results]
        if not batch:
            continue
        try:
            result = batch_query(batch)
            all_results.update(result)
            if i % 500 == 0:
                print(f"  {i}/{len(qids)} — {len(all_results)} total")
                # Save progress
                with open(OUTPUT, "w", encoding="utf-8") as f:
                    json.dump(all_results, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"  ERROR at {i}: {e}")
            time.sleep(15)
        time.sleep(2)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(all_results)} Wikidata labels → {OUTPUT}")


if __name__ == "__main__":
    asyncio.run(main())
