"""Fetch additional Buddhist temples from OSM Overpass API for extended regions.

Targets:
  A. Previously timed-out: Mongolia, Singapore
  B. New regions: Bangladesh, Pakistan, Russia, USA, Canada, Australia,
     Germany, UK, France, Brazil

Real data only — skip failures, never synthesize.
"""
import json
import time
import urllib.parse
import urllib.request

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "FoJinBot/1.0 (https://fojin.app)"
OUTPUT = "data/osm_extended_temples.json"

COUNTRIES = [
    # (中文名, ISO 2-letter)
    # A. Previously timed out
    ("蒙古", "MN"),
    ("新加坡", "SG"),
    # B. New regions
    ("孟加拉国", "BD"),
    ("巴基斯坦", "PK"),
    ("俄罗斯", "RU"),
    ("美国", "US"),
    ("加拿大", "CA"),
    ("澳大利亚", "AU"),
    ("德国", "DE"),
    ("英国", "GB"),
    ("法国", "FR"),
    ("巴西", "BR"),
]


def build_query(iso: str, timeout: int = 600) -> str:
    return f"""
[out:json][timeout:{timeout}];
area["ISO3166-1"="{iso}"]->.a;
(
  node["amenity"="place_of_worship"]["religion"="buddhist"](area.a);
  way["amenity"="place_of_worship"]["religion"="buddhist"](area.a);
  relation["amenity"="place_of_worship"]["religion"="buddhist"](area.a);
);
out center tags;
"""


def query_overpass(q: str, timeout: int = 620) -> dict:
    data = urllib.parse.urlencode({"data": q}).encode()
    req = urllib.request.Request(OVERPASS_URL, data=data, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
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
        name_ja = tags.get("name:ja", "")
        name_ko = tags.get("name:ko", "")
        name_en = tags.get("name:en", "")
        name_local = tags.get("name", "")

        # Preference by country
        if country in ("新加坡",):
            primary = name_zh or name_local or name_en
        else:
            primary = name_zh or name_ja or name_ko or name_local or name_en

        if not primary or not primary.strip():
            continue

        records.append({
            "osm_id": f"{el['type']}/{el['id']}",
            "country": country,
            "name_primary": primary,
            "name_zh": name_zh,
            "name_ja": name_ja,
            "name_ko": name_ko,
            "name_en": name_en,
            "latitude": lat,
            "longitude": lng,
            "denomination": tags.get("denomination", ""),
            "wikidata": tags.get("wikidata", ""),
        })
    return records


def fetch_country(name: str, iso: str, max_retries: int = 2):
    """Fetch with retry on 429. Returns (records, status, note)."""
    for attempt in range(max_retries + 1):
        t0 = time.time()
        try:
            data = query_overpass(build_query(iso))
            elapsed = time.time() - t0
            recs = extract(data, name)
            note = f"{len(data.get('elements', []))} elements → {len(recs)} named ({elapsed:.1f}s)"
            return recs, "OK", note
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 45 * (attempt + 1)
                print(f"  429 rate-limited, waiting {wait}s (attempt {attempt+1})")
                time.sleep(wait)
                continue
            if e.code == 504:
                return [], "TIMEOUT", f"HTTP 504 gateway timeout after {time.time()-t0:.1f}s"
            return [], "ERROR", f"HTTP {e.code}: {e}"
        except Exception as e:
            msg = str(e)
            if "timed out" in msg.lower() or "timeout" in msg.lower():
                return [], "TIMEOUT", f"client timeout after {time.time()-t0:.1f}s"
            return [], "ERROR", msg
    return [], "ERROR", "retries exhausted"


def main():
    all_records = []
    report = []

    for name, iso in COUNTRIES:
        print(f"\nQuerying {name} ({iso})...")
        recs, status, note = fetch_country(name, iso)
        print(f"  {status}: {note}")
        all_records.extend(recs)
        report.append({"country": name, "iso": iso, "count": len(recs), "status": status, "note": note})
        time.sleep(6)  # polite delay

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)

    print(f"\n=== SUMMARY ===")
    print(f"Total: {len(all_records)} records → {OUTPUT}")
    for r in report:
        print(f"  [{r['status']}] {r['country']} ({r['iso']}): {r['count']}")

    # Write report alongside
    with open("data/osm_extended_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
