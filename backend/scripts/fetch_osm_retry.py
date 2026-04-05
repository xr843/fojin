"""Retry failed OSM queries + detailed China provincial queries."""
import json
import time
import urllib.parse
import urllib.request

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "FoJinBot/1.0 (https://fojin.app)"
OUTPUT = "data/osm_retry_temples.json"

# Retry failed countries with bbox queries (more reliable than area)
TARGETS = [
    # (name, query_type, args)
    ("印度", "iso", "IN"),
    ("尼泊尔", "iso", "NP"),
    ("蒙古", "iso", "MN"),
    ("新加坡", "iso", "SG"),
]


def build_query_iso(iso: str) -> str:
    return f"""
[out:json][timeout:600];
area["ISO3166-1"="{iso}"]->.a;
(
  node["amenity"="place_of_worship"]["religion"="buddhist"](area.a);
  way["amenity"="place_of_worship"]["religion"="buddhist"](area.a);
  relation["amenity"="place_of_worship"]["religion"="buddhist"](area.a);
);
out center tags;
"""


def query_overpass(q: str) -> dict:
    data = urllib.parse.urlencode({"data": q}).encode()
    req = urllib.request.Request(OVERPASS_URL, data=data, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read())


def extract(data: dict, country: str) -> list[dict]:
    records = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        if el["type"] == "node":
            lat, lng = el.get("lat"), el.get("lon")
        else:
            c = el.get("center", {})
            lat, lng = c.get("lat"), c.get("lon")
        if lat is None or lng is None:
            continue

        name_zh = tags.get("name:zh") or tags.get("name:zh-Hans") or tags.get("name:zh-Hant") or ""
        name_en = tags.get("name:en", "")
        name_local = tags.get("name", "")
        primary = name_zh or name_local or name_en

        if not primary:
            continue

        records.append({
            "osm_id": f"{el['type']}/{el['id']}",
            "country": country,
            "name_primary": primary,
            "name_zh": name_zh,
            "name_ja": tags.get("name:ja", ""),
            "name_ko": tags.get("name:ko", ""),
            "name_en": name_en,
            "latitude": lat,
            "longitude": lng,
            "denomination": tags.get("denomination", ""),
            "wikidata": tags.get("wikidata", ""),
        })
    return records


def main():
    all_records = []
    for name, qtype, arg in TARGETS:
        print(f"\nFetching {name}...")
        t0 = time.time()
        try:
            if qtype == "iso":
                data = query_overpass(build_query_iso(arg))
            recs = extract(data, name)
            print(f"  {name}: {len(recs)} temples ({time.time()-t0:.1f}s)")
            all_records.extend(recs)
        except Exception as e:
            print(f"  ERROR: {e}")
        time.sleep(10)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)
    print(f"\nTotal: {len(all_records)} → {OUTPUT}")


if __name__ == "__main__":
    main()
