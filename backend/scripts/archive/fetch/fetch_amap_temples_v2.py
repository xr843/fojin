"""Fetch Chinese Buddhist temples from Amap POI API — v2: search by city for full coverage.

V1 searched by province and hit 500-result caps in populous provinces.
V2 searches by prefecture-level city (~340 cities) to avoid truncation.

Output: data/amap_temples_v2.json
"""
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

AMAP_KEY = os.environ.get("AMAP_KEY")
if not AMAP_KEY:
    sys.exit("ERROR: AMAP_KEY environment variable is not set (check .env)")
AMAP_URL = "https://restapi.amap.com/v3/place/text"
AMAP_DISTRICT_URL = "https://restapi.amap.com/v3/config/district"
USER_AGENT = "FoJinBot/1.0"
OUTPUT = "data/amap_temples_v2.json"

KEYWORDS = ["寺", "庵", "禅寺", "佛寺", "佛教", "精舍", "佛堂"]

SKIP_WORDS = ["清真", "教堂", "基督", "天主", "道观", "道教", "伊斯兰",
              "关帝", "妈祖", "城隍", "土地庙", "孔庙", "文庙",
              "殡仪", "墓", "陵园", "酒店", "宾馆", "饭店", "餐厅",
              "停车", "公厕", "超市", "药店", "医院", "学校",
              "公园", "广场", "商场", "写字楼", "小区", "花园"]


def _transform_lat(x, y):
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * math.pi) + 320.0 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lon(x, y):
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return ret


def gcj02_to_wgs84(lng, lat):
    a = 6378245.0
    ee = 0.00669342162296594323
    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lon(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - ee * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * math.pi)
    dlng = (dlng * 180.0) / (a / sqrtmagic * math.cos(radlat) * math.pi)
    return lng - dlng, lat - dlat


def get_cities() -> list[dict]:
    """Fetch all prefecture-level cities from Amap district API."""
    params = urllib.parse.urlencode({
        "key": AMAP_KEY,
        "keywords": "中国",
        "subdistrict": 2,
        "extensions": "base",
    })
    url = f"{AMAP_DISTRICT_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())

    cities = []
    for province in data.get("districts", [{}])[0].get("districts", []):
        pname = province.get("name", "")
        for city in province.get("districts", []):
            cities.append({
                "adcode": city.get("adcode", ""),
                "name": city.get("name", ""),
                "province": pname,
            })
        # Direct-administered municipalities: province itself is the city
        if not province.get("districts"):
            cities.append({
                "adcode": province.get("adcode", ""),
                "name": pname,
                "province": pname,
            })
    return cities


def amap_search(keyword: str, city_code: str, page: int = 1) -> dict:
    params = urllib.parse.urlencode({
        "key": AMAP_KEY,
        "keywords": keyword,
        "city": city_code,
        "citylimit": "true",
        "offset": 25,
        "page": page,
        "output": "json",
        "extensions": "base",
    })
    url = f"{AMAP_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def main():
    print("Fetching city list...")
    cities = get_cities()
    print(f"Got {len(cities)} cities")

    all_pois: dict[str, dict] = {}
    total_requests = 0

    for ci, city in enumerate(cities):
        city_before = len(all_pois)
        for keyword in KEYWORDS:
            page = 1
            while page <= 20:
                try:
                    data = amap_search(keyword, city["adcode"], page)
                    total_requests += 1
                    time.sleep(0.25)
                except Exception as e:
                    print(f"  ERR {city['name']}/{keyword}: {e}")
                    time.sleep(2)
                    break

                if data.get("status") != "1":
                    break

                pois = data.get("pois", [])
                if not pois:
                    break

                for poi in pois:
                    pid = poi.get("id", "")
                    name = poi.get("name", "")
                    location = poi.get("location", "")
                    if not pid or not name or not location:
                        continue
                    if any(w in name for w in SKIP_WORDS):
                        continue
                    if pid in all_pois:
                        continue
                    try:
                        lng_gcj, lat_gcj = [float(x) for x in location.split(",")]
                        lng_wgs, lat_wgs = gcj02_to_wgs84(lng_gcj, lat_gcj)
                    except (ValueError, IndexError):
                        continue

                    all_pois[pid] = {
                        "amap_id": pid,
                        "name": name,
                        "latitude": round(lat_wgs, 7),
                        "longitude": round(lng_wgs, 7),
                        "address": poi.get("address", ""),
                        "province": poi.get("pname", city["province"]),
                        "city": poi.get("cityname", city["name"]),
                        "district": poi.get("adname", ""),
                        "type": poi.get("type", ""),
                        "typecode": poi.get("typecode", ""),
                    }

                count = int(data.get("count", 0))
                if page * 25 >= count or page * 25 >= 500:
                    break
                page += 1

        city_new = len(all_pois) - city_before
        if (ci + 1) % 20 == 0 or ci == len(cities) - 1:
            print(f"[{ci+1}/{len(cities)}] {city['province']}/{city['name']}: +{city_new} (total: {len(all_pois)}, reqs: {total_requests})")

    # Save
    result = list(all_pois.values())
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n{'='*60}")
    print(f"Total: {len(result)} POIs, {total_requests} API requests")
    print(f"Saved to {OUTPUT}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
