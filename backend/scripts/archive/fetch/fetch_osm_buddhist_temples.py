"""Fetch Buddhist temples from OpenStreetMap via Overpass API.

OSM has comprehensive coverage of Buddhist temples worldwide,
tagged with amenity=place_of_worship + religion=buddhist.

Run locally.
"""
import json
import time
import urllib.parse
import urllib.request

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "FoJinBot/1.0 (https://fojin.app)"
OUTPUT = "data/osm_buddhist_temples.json"

COUNTRIES = {
    "中国": "CN",
    "日本": "JP",
    "韩国": "KR",
    "朝鲜": "KP",
    "台湾": "TW",
    "越南": "VN",
    "泰国": "TH",
    "缅甸": "MM",
    "斯里兰卡": "LK",
    "柬埔寨": "KH",
    "老挝": "LA",
    "尼泊尔": "NP",
    "不丹": "BT",
    "蒙古": "MN",
    "印度": "IN",
    "新加坡": "SG",
    "马来西亚": "MY",
    "印度尼西亚": "ID",
}


def build_query(country_iso: str) -> str:
    return f"""
[out:json][timeout:300];
area["ISO3166-1"="{country_iso}"]->.searchArea;
(
  node["amenity"="place_of_worship"]["religion"="buddhist"](area.searchArea);
  way["amenity"="place_of_worship"]["religion"="buddhist"](area.searchArea);
  relation["amenity"="place_of_worship"]["religion"="buddhist"](area.searchArea);
);
out center tags;
"""


def query_overpass(q: str) -> dict:
    data = urllib.parse.urlencode({"data": q}).encode()
    req = urllib.request.Request(OVERPASS_URL, data=data, headers={
        "User-Agent": USER_AGENT,
    })
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read())


def extract_records(data: dict, country: str) -> list[dict]:
    records = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        # Get coordinates
        if el["type"] == "node":
            lat, lng = el.get("lat"), el.get("lon")
        else:
            center = el.get("center", {})
            lat, lng = center.get("lat"), center.get("lon")

        if lat is None or lng is None:
            continue

        # Get names
        name_zh = tags.get("name:zh") or tags.get("name:zh-Hans") or tags.get("name:zh-Hant") or ""
        name_ja = tags.get("name:ja", "")
        name_ko = tags.get("name:ko", "")
        name_en = tags.get("name:en", "")
        name_local = tags.get("name", "")

        # Prefer native script
        if country == "中国" or country == "台湾":
            primary = name_zh or name_local or name_en
        elif country == "日本":
            primary = name_ja or name_local or name_en
        elif country == "韩国" or country == "朝鲜":
            primary = name_ko or name_local or name_en
        else:
            primary = name_local or name_en

        if not primary or len(primary.strip()) < 1:
            continue

        records.append({
            "osm_id": f"{el['type']}/{el['id']}",
            "country": country,
            "name_primary": primary,
            "name_zh": name_zh or (name_local if country in ("中国", "台湾") else ""),
            "name_ja": name_ja or (name_local if country == "日本" else ""),
            "name_ko": name_ko or (name_local if country in ("韩国", "朝鲜") else ""),
            "name_en": name_en,
            "latitude": lat,
            "longitude": lng,
            "denomination": tags.get("denomination", ""),
            "wikidata": tags.get("wikidata", ""),
        })
    return records


def main():
    all_records = []

    for country_name, iso in COUNTRIES.items():
        print(f"\nQuerying {country_name} ({iso})...")
        t0 = time.time()
        try:
            data = query_overpass(build_query(iso))
        except Exception as e:
            print(f"  ERROR: {e}")
            time.sleep(30)
            continue

        elapsed = time.time() - t0
        records = extract_records(data, country_name)
        print(f"  Got {len(data.get('elements', []))} elements, extracted {len(records)} temples ({elapsed:.1f}s)")
        all_records.extend(records)
        time.sleep(5)  # Be polite to Overpass

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)

    print(f"\nTotal: {len(all_records)} OSM Buddhist temples → {OUTPUT}")
    from collections import Counter
    counts = Counter(r["country"] for r in all_records)
    for c, n in counts.most_common():
        print(f"  {c}: {n}")


if __name__ == "__main__":
    main()
