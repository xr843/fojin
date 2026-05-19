"""Fetch Buddhist persons with birth/death place coordinates from Wikidata.

Targets famous historical Buddhist figures: translators, masters, founders.
Produces: data/buddhist_persons.json
"""
import json
import time
import urllib.parse
import urllib.request

WIKIDATA_URL = "https://query.wikidata.org/sparql"
USER_AGENT = "FoJinBot/1.0 (https://fojin.app; Buddhist studies platform)"
OUTPUT = "data/buddhist_persons.json"

# Multiple queries to capture different aspects
QUERIES = {
    "buddhist_clergy_with_birth": """
SELECT ?item ?itemLabel ?zhLabel ?jaLabel ?coord ?placeLabel WHERE {
  {
    ?item wdt:P106/wdt:P279* wd:Q4263842 .  # Buddhist monk
  } UNION {
    ?item wdt:P106/wdt:P279* wd:Q1662844 .  # Buddhist priest
  } UNION {
    ?item wdt:P106 wd:Q193391 .              # Buddhist teacher
  } UNION {
    ?item wdt:P106 wd:Q161598 .              # Buddhist nun
  }
  ?item wdt:P19 ?place .                    # birth place
  ?place wdt:P625 ?coord .
  OPTIONAL { ?item rdfs:label ?zhLabel FILTER(LANG(?zhLabel) = "zh") }
  OPTIONAL { ?item rdfs:label ?jaLabel FILTER(LANG(?jaLabel) = "ja") }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . ?place rdfs:label ?placeLabel . }
} LIMIT 5000
""",
    "buddhism_religion_persons": """
SELECT ?item ?itemLabel ?zhLabel ?jaLabel ?coord ?placeLabel WHERE {
  ?item wdt:P140 wd:Q748 .                 # religion: Buddhism
  ?item wdt:P31 wd:Q5 .                    # is human
  ?item wdt:P19 ?place .
  ?place wdt:P625 ?coord .
  OPTIONAL { ?item rdfs:label ?zhLabel FILTER(LANG(?zhLabel) = "zh") }
  OPTIONAL { ?item rdfs:label ?jaLabel FILTER(LANG(?jaLabel) = "ja") }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . ?place rdfs:label ?placeLabel . }
} LIMIT 5000
""",
    "japanese_buddhist": """
SELECT ?item ?itemLabel ?zhLabel ?jaLabel ?coord ?placeLabel WHERE {
  ?item wdt:P106/wdt:P279* wd:Q4263842 .
  ?item wdt:P27 wd:Q17 .                    # citizen of Japan
  {
    ?item wdt:P19 ?place .
  } UNION {
    ?item wdt:P20 ?place .                  # death place
  }
  ?place wdt:P625 ?coord .
  OPTIONAL { ?item rdfs:label ?zhLabel FILTER(LANG(?zhLabel) = "zh") }
  OPTIONAL { ?item rdfs:label ?jaLabel FILTER(LANG(?jaLabel) = "ja") }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . ?place rdfs:label ?placeLabel . }
} LIMIT 5000
""",
    "chinese_buddhist": """
SELECT ?item ?itemLabel ?zhLabel ?coord ?placeLabel WHERE {
  ?item wdt:P106/wdt:P279* wd:Q4263842 .
  ?item wdt:P27/wdt:P279* wd:Q148 .         # citizen of China
  {
    ?item wdt:P19 ?place .
  } UNION {
    ?item wdt:P20 ?place .
  }
  ?place wdt:P625 ?coord .
  OPTIONAL { ?item rdfs:label ?zhLabel FILTER(LANG(?zhLabel) = "zh") }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . ?place rdfs:label ?placeLabel . }
} LIMIT 3000
""",
}


def sparql_query(q: str) -> list[dict]:
    params = urllib.parse.urlencode({"query": q, "format": "json"})
    url = f"{WIKIDATA_URL}?{params}"
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/sparql-results+json",
    })
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read())
    return data.get("results", {}).get("bindings", [])


def parse_point(coord: str) -> tuple[float, float] | None:
    if not coord.startswith("Point("):
        return None
    inner = coord.removeprefix("Point(").removesuffix(")")
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
    seen = set()

    for name, q in QUERIES.items():
        print(f"\nQuery: {name}")
        t0 = time.time()
        try:
            bindings = sparql_query(q)
        except Exception as e:
            print(f"  ERROR: {e}")
            time.sleep(15)
            continue
        print(f"  Got {len(bindings)} results ({time.time()-t0:.1f}s)")

        added = 0
        for b in bindings:
            wid = b.get("item", {}).get("value", "").split("/")[-1]
            if not wid or wid in seen:
                continue
            coord = parse_point(b.get("coord", {}).get("value", ""))
            if not coord:
                continue
            lat, lng = coord

            name_en = b.get("itemLabel", {}).get("value", "")
            name_zh = b.get("zhLabel", {}).get("value", "")
            name_ja = b.get("jaLabel", {}).get("value", "")
            place_name = b.get("placeLabel", {}).get("value", "")

            if name_en.startswith("Q") and name_en[1:].isdigit():
                name_en = ""
            if not (name_zh or name_en or name_ja):
                continue

            seen.add(wid)
            all_records.append({
                "wikidata_id": wid,
                "name_zh": name_zh,
                "name_en": name_en,
                "name_ja": name_ja,
                "place_name": place_name,
                "latitude": lat,
                "longitude": lng,
                "source_query": name,
            })
            added += 1

        print(f"  Added {added} unique")
        time.sleep(3)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)

    print(f"\nTotal: {len(all_records)} Buddhist persons with coords → {OUTPUT}")
    print(f"  with name_zh: {sum(1 for r in all_records if r['name_zh'])}")
    print(f"  with name_ja: {sum(1 for r in all_records if r['name_ja'])}")


if __name__ == "__main__":
    main()
