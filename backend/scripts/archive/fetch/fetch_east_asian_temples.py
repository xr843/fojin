"""
Fetch East Asian Buddhist temples from Wikidata (China, Japan, Korea, Vietnam, Taiwan).

Run locally to avoid server IP rate limiting.
Produces: data/east_asian_temples.json for import.
"""
import json
import time
import urllib.parse
import urllib.request

WIKIDATA_URL = "https://query.wikidata.org/sparql"
USER_AGENT = "FoJinBot/1.0 (https://fojin.app; Buddhist studies platform)"
OUTPUT = "data/east_asian_temples.json"

COUNTRIES = {
    "中国": ("Q148", "China"),
    "日本": ("Q17", "Japan"),
    "韩国": ("Q884", "South Korea"),
    "朝鲜": ("Q423", "North Korea"),
    "越南": ("Q881", "Vietnam"),
    "台湾": ("Q865", "Taiwan"),
    "香港": ("Q8646", "Hong Kong"),
    "澳门": ("Q14773", "Macau"),
}

def build_query(country_q: str) -> str:
    return f"""
SELECT ?item ?itemLabel ?itemLabelZh ?itemLabelJa ?coord WHERE {{
  {{
    ?item wdt:P31/wdt:P279* wd:Q5393308 .  # Buddhist temple
  }} UNION {{
    ?item wdt:P31/wdt:P279* wd:Q160742 .   # Buddhist monastery
  }} UNION {{
    ?item wdt:P31/wdt:P279* wd:Q178561 .   # stupa
  }} UNION {{
    ?item wdt:P31/wdt:P279* wd:Q1030034 .  # cave temple
  }} UNION {{
    ?item wdt:P31/wdt:P279* wd:Q56242071 . # Chan temple
  }}
  ?item wdt:P17 wd:{country_q} .
  ?item wdt:P625 ?coord .
  OPTIONAL {{ ?item rdfs:label ?itemLabelZh FILTER(LANG(?itemLabelZh) = "zh") }}
  OPTIONAL {{ ?item rdfs:label ?itemLabelJa FILTER(LANG(?itemLabelJa) = "ja") }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
}} LIMIT 3000
"""


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
    seen_qids = set()

    for country_name, (q_id, en_name) in COUNTRIES.items():
        print(f"\nFetching {country_name} ({en_name})...")
        t0 = time.time()
        try:
            bindings = sparql_query(build_query(q_id))
        except Exception as e:
            print(f"  ERROR: {e}")
            time.sleep(10)
            continue
        print(f"  Got {len(bindings)} raw results ({time.time()-t0:.1f}s)")

        added = 0
        for b in bindings:
            wid = b.get("item", {}).get("value", "").split("/")[-1]
            if not wid or wid in seen_qids:
                continue
            coord = parse_point(b.get("coord", {}).get("value", ""))
            if not coord:
                continue
            lat, lng = coord

            name_en = b.get("itemLabel", {}).get("value", "")
            name_zh = b.get("itemLabelZh", {}).get("value", "")
            name_ja = b.get("itemLabelJa", {}).get("value", "")

            if name_en.startswith("Q") and name_en[1:].isdigit():
                name_en = ""
            if not (name_zh or name_en or name_ja):
                continue

            seen_qids.add(wid)
            all_records.append({
                "wikidata_id": wid,
                "country": country_name,
                "name_zh": name_zh,
                "name_en": name_en,
                "name_ja": name_ja,
                "latitude": lat,
                "longitude": lng,
            })
            added += 1

        print(f"  Added {added} unique records")
        time.sleep(3)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)

    print(f"\nTotal: {len(all_records)} East Asian Buddhist temples → {OUTPUT}")
    # Summary by country
    from collections import Counter
    by_country = Counter(r["country"] for r in all_records)
    for c, n in by_country.most_common():
        print(f"  {c}: {n}")


if __name__ == "__main__":
    main()
