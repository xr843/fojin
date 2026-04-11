"""Fetch Chinese Buddhist temples from Amap (高德地图) POI API.

Strategy:
- Search by province (31 provinces) to avoid hitting per-query limits
- Keywords: 佛教寺院|寺庙|禅寺|佛寺|庵|精舍
- Type code: 141201 (宗教活动场所)
- Paginate up to 25 pages per province (500 results max per province per query)
- Convert GCJ-02 → WGS-84 coordinates
- Rate limit: ~0.3s between requests

Output: data/amap_temples.json
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
USER_AGENT = "FoJinBot/1.0"
OUTPUT = "data/amap_temples.json"

# 31 provinces + municipalities + autonomous regions
PROVINCES = [
    "北京", "天津", "上海", "重庆",
    "河北", "山西", "辽宁", "吉林", "黑龙江",
    "江苏", "浙江", "安徽", "福建", "江西", "山东",
    "河南", "湖北", "湖南", "广东", "海南",
    "四川", "贵州", "云南", "陕西", "甘肃", "青海",
    "台湾", "广西", "内蒙古", "西藏", "宁夏", "新疆",
]

KEYWORDS = [
    "寺",
    "禅寺",
    "佛寺",
    "寺庙",
    "佛教寺院",
    "庵",
    "精舍",
]


# ── GCJ-02 → WGS-84 conversion ──

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
    """Convert GCJ-02 (高德) to WGS-84 coordinates."""
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


def amap_search(keyword: str, city: str, page: int = 1) -> dict:
    params = urllib.parse.urlencode({
        "key": AMAP_KEY,
        "keywords": keyword,
        # "types": "141201",  # removed: too restrictive
        "city": city,
        "citylimit": "true",
        "offset": 20,
        "page": page,
        "output": "json",
        "extensions": "base",
    })
    url = f"{AMAP_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def main():
    all_pois: dict[str, dict] = {}  # amap_id → record
    total_requests = 0
    skip_words = ["清真", "教堂", "基督", "天主", "道观", "道教", "伊斯兰",
                  "关帝", "妈祖", "城隍", "土地庙", "孔庙", "文庙",
                  "殡仪", "墓", "陵园"]

    for province in PROVINCES:
        for keyword in KEYWORDS:
            page = 1
            while page <= 25:
                try:
                    data = amap_search(keyword, province, page)
                    total_requests += 1
                    time.sleep(0.35)
                except Exception as e:
                    print(f"  ERROR {province}/{keyword} p{page}: {e}")
                    time.sleep(2)
                    break

                if data.get("status") != "1":
                    print(f"  API error {province}/{keyword}: {data.get('info', '?')}")
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

                    # Filter non-Buddhist
                    if any(w in name for w in skip_words):
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
                        "province": poi.get("pname", province),
                        "city": poi.get("cityname", ""),
                        "district": poi.get("adname", ""),
                        "type": poi.get("type", ""),
                        "typecode": poi.get("typecode", ""),
                    }

                count = int(data.get("count", 0))
                if page * 20 >= count or page * 20 >= 500:
                    break
                page += 1

        print(f"[{province}] cumulative: {len(all_pois)} temples, {total_requests} requests")

    # Save
    result = list(all_pois.values())
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n{'='*60}")
    print(f"Total: {len(result)} temples, {total_requests} API requests")
    print(f"Saved to {OUTPUT}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
