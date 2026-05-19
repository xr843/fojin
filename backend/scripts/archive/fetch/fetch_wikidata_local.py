"""
Fetch Wikidata coordinates locally and save to JSON for server import.

Run this from a machine that can access Wikidata SPARQL (not rate-limited VPS).
Then copy the JSON file to the server and run enrich_from_json.py.

Usage:
    python scripts/fetch_wikidata_local.py
    # produces data/wikidata_geo.json
"""
import json
import time
import urllib.request
import urllib.parse

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
USER_AGENT = "FoJinBot/1.0 (https://fojin.app; Buddhist studies platform)"
OUTPUT = "data/wikidata_geo.json"

QUERIES = {
    "buddhist_monasteries": """
SELECT ?item ?itemLabel ?itemLabelZh ?coord WHERE {
  { ?item wdt:P31/wdt:P279* wd:Q160742 . }
  UNION { ?item wdt:P31/wdt:P279* wd:Q5393308 . }
  UNION { ?item wdt:P31/wdt:P279* wd:Q178561 . }
  UNION { ?item wdt:P31/wdt:P279* wd:Q1030034 . }
  ?item wdt:P625 ?coord .
  OPTIONAL { ?item rdfs:label ?itemLabelZh FILTER(LANG(?itemLabelZh) = "zh") }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . }
} LIMIT 5000
""",
    "buddhist_persons": """
SELECT ?item ?itemLabel ?itemLabelZh ?coord ?placeLabel WHERE {
  {
    ?item wdt:P106/wdt:P279* wd:Q4263842 .
  } UNION {
    ?item wdt:P106/wdt:P279* wd:Q1662844 .
  } UNION {
    ?item wdt:P140 wd:Q748 .
    ?item wdt:P106/wdt:P279* wd:Q1234713 .
  }
  {
    ?item wdt:P19 ?place .
  } UNION {
    ?item wdt:P20 ?place .
  }
  ?place wdt:P625 ?coord .
  OPTIONAL { ?item rdfs:label ?itemLabelZh FILTER(LANG(?itemLabelZh) = "zh") }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . }
} LIMIT 3000
""",
}


def query_sparql(sparql: str) -> list[dict]:
    params = urllib.parse.urlencode({"query": sparql, "format": "json"})
    url = f"{WIKIDATA_SPARQL_URL}?{params}"
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/sparql-results+json",
    })
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    return data.get("results", {}).get("bindings", [])


def parse_point(coord_str: str) -> tuple[float, float] | None:
    if not coord_str.startswith("Point("):
        return None
    inner = coord_str.removeprefix("Point(").removesuffix(")")
    parts = inner.split()
    if len(parts) != 2:
        return None
    try:
        lng, lat = float(parts[0]), float(parts[1])
        if -180 <= lng <= 180 and -90 <= lat <= 90:
            return lat, lng
    except ValueError:
        pass
    return None


def main():
    all_records = []

    for name, sparql in QUERIES.items():
        print(f"Querying: {name}...")
        t0 = time.time()
        bindings = query_sparql(sparql)
        print(f"  Got {len(bindings)} results ({time.time()-t0:.1f}s)")

        seen = set()
        for b in bindings:
            wid = b.get("item", {}).get("value", "").split("/")[-1]
            if not wid or wid in seen:
                continue
            seen.add(wid)

            coord_val = b.get("coord", {}).get("value", "")
            parsed = parse_point(coord_val)
            if not parsed:
                continue
            lat, lng = parsed

            name_en = b.get("itemLabel", {}).get("value", "")
            name_zh = b.get("itemLabelZh", {}).get("value", "")
            place_name = b.get("placeLabel", {}).get("value", "")

            if name_en.startswith("Q") and name_en[1:].isdigit():
                name_en = ""
            if not name_zh and not name_en:
                continue

            all_records.append({
                "source": name,
                "wikidata_id": wid,
                "name_zh": name_zh,
                "name_en": name_en,
                "place_name": place_name,
                "latitude": lat,
                "longitude": lng,
            })

        print(f"  Extracted {len(seen)} unique records")
        time.sleep(3)  # Be polite

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)

    print(f"\nSaved {len(all_records)} records to {OUTPUT}")


if __name__ == "__main__":
    main()
