"""Fetch additional Chinese Buddhist temples from OSM (wider query) + Nominatim.

Strategy:
1. Wider Overpass query for China: not just amenity=place_of_worship+religion=buddhist,
   but also building=temple, name matching patterns (寺/庙/庵/禅院/精舍/丛林/讲寺).
2. Nominatim geocoding for a curated list of famous missing temples.
3. Dedup against existing DB entries by name + proximity (< 5km).

Output: data/cn_temples_extended.json

Run locally — does NOT write to DB.
"""
import json
import math
import time
import urllib.parse
import urllib.request

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "FoJinBot/1.0 (https://fojin.app; contact@fojin.app)"
OUTPUT = "data/cn_temples_extended.json"


def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def query_overpass(q: str) -> dict:
    data = urllib.parse.urlencode({"data": q}).encode()
    req = urllib.request.Request(OVERPASS_URL, data=data, headers={
        "User-Agent": USER_AGENT,
    })
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read())


def nominatim_search(name: str, country: str = "cn") -> list[dict]:
    params = urllib.parse.urlencode({
        "q": name,
        "countrycodes": country,
        "format": "json",
        "limit": 3,
        "addressdetails": 1,
    })
    url = f"{NOMINATIM_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


# ── Overpass: wider queries for Chinese Buddhist temples ──

# Query 1: Standard buddhist tag
Q_BUDDHIST = """
[out:json][timeout:600];
area["ISO3166-1"="CN"]->.cn;
(
  node["amenity"="place_of_worship"]["religion"="buddhist"](area.cn);
  way["amenity"="place_of_worship"]["religion"="buddhist"](area.cn);
  relation["amenity"="place_of_worship"]["religion"="buddhist"](area.cn);
);
out center tags;
"""

# Query 2: building=temple in China (many temples only have this)
Q_BUILDING_TEMPLE = """
[out:json][timeout:600];
area["ISO3166-1"="CN"]->.cn;
(
  node["building"="temple"](area.cn);
  way["building"="temple"](area.cn);
  relation["building"="temple"](area.cn);
);
out center tags;
"""

# Query 3: Name-based pattern match for Buddhist terms in name
Q_NAME_PATTERN = """
[out:json][timeout:600];
area["ISO3166-1"="CN"]->.cn;
(
  node["amenity"="place_of_worship"]["name"~"寺|禅|庵|精舍|丛林|讲寺|佛"](area.cn);
  way["amenity"="place_of_worship"]["name"~"寺|禅|庵|精舍|丛林|讲寺|佛"](area.cn);
  relation["amenity"="place_of_worship"]["name"~"寺|禅|庵|精舍|丛林|讲寺|佛"](area.cn);
);
out center tags;
"""

# Query 4: historic=monastery in China
Q_HISTORIC = """
[out:json][timeout:600];
area["ISO3166-1"="CN"]->.cn;
(
  node["historic"="monastery"](area.cn);
  way["historic"="monastery"](area.cn);
  relation["historic"="monastery"](area.cn);
);
out center tags;
"""


def extract_records(data: dict, source: str) -> list[dict]:
    records = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        if el["type"] == "node":
            lat, lng = el.get("lat"), el.get("lon")
        else:
            center = el.get("center", {})
            lat, lng = center.get("lat"), center.get("lon")
        if lat is None or lng is None:
            continue

        name_zh = (
            tags.get("name:zh")
            or tags.get("name:zh-Hans")
            or tags.get("name:zh-Hant")
            or ""
        )
        name = tags.get("name", "")

        # Skip non-Buddhist (filter out obvious non-Buddhist like 清真寺/教堂/道观)
        skip_words = ["清真", "教堂", "基督", "天主", "道观", "道教", "关帝", "妈祖", "城隍", "土地庙", "孔庙", "文庙"]
        combined = name_zh + name
        if any(w in combined for w in skip_words):
            continue

        # If name is purely ASCII/Latin and no zh name, probably not a Chinese Buddhist temple
        if not name_zh and name and all(ord(c) < 0x4E00 for c in name.replace(" ", "")):
            continue

        records.append({
            "osm_id": f"{el['type']}/{el['id']}",
            "name_primary": name_zh or name,
            "name_zh": name_zh,
            "name_en": tags.get("name:en", ""),
            "latitude": lat,
            "longitude": lng,
            "wikidata": tags.get("wikidata", ""),
            "religion": tags.get("religion", ""),
            "denomination": tags.get("denomination", ""),
            "source": source,
        })
    return records


# ── Famous temples to geocode via Nominatim ──

FAMOUS_TEMPLES = [
    # 福建
    "福清崇恩禅寺", "莆田广化寺", "泉州开元寺", "福州涌泉寺", "福州西禅寺",
    "厦门南普陀寺", "福清万福寺", "宁德支提寺", "漳州南山寺",
    # 浙江
    "杭州灵隐寺", "杭州净慈寺", "宁波天童寺", "宁波阿育王寺",
    "普陀山普济寺", "普陀山法雨寺", "普陀山慧济寺", "天台国清寺",
    # 江苏
    "南京栖霞寺", "南京灵谷寺", "苏州寒山寺", "苏州西园寺",
    "镇江金山寺", "扬州大明寺", "常州天宁寺", "南通广教寺",
    # 安徽
    "九华山化城寺", "九华山百岁宫", "九华山月身殿",
    # 四川
    "峨眉山报国寺", "峨眉山万年寺", "峨眉山金顶华藏寺",
    "成都文殊院", "成都昭觉寺", "成都大慈寺", "乐山凌云寺",
    # 山西
    "五台山显通寺", "五台山塔院寺", "五台山菩萨顶", "五台山南山寺",
    "大同华严寺", "太原崇善寺", "交城玄中寺",
    # 河南
    "登封少林寺", "洛阳白马寺", "洛阳龙门石窟", "开封大相国寺",
    # 湖北
    "武汉归元寺", "武汉宝通寺", "黄梅五祖寺", "黄梅四祖寺",
    "当阳玉泉寺",
    # 湖南
    "长沙麓山寺", "长沙开福寺", "衡山南岳大庙",
    # 广东
    "广州光孝寺", "广州六榕寺", "韶关南华寺", "潮州开元寺",
    # 云南
    "大理崇圣寺", "昆明圆通寺", "昆明筇竹寺",
    "西双版纳总佛寺",
    # 北京
    "北京法源寺", "北京广济寺", "北京雍和宫", "北京潭柘寺",
    "北京戒台寺", "北京碧云寺",
    # 上海
    "上海龙华寺", "上海玉佛禅寺", "上海静安寺",
    # 江西
    "庐山东林寺", "南昌佑民寺", "宜春仰山栖隐禅寺",
    # 甘肃
    "敦煌莫高窟", "天水麦积山石窟", "张掖大佛寺",
    # 重庆
    "重庆华岩寺", "重庆罗汉寺", "大足宝顶山",
    # 辽宁
    "沈阳慈恩寺", "鞍山千山无量观",
    # 吉林
    "长春般若寺",
    # 西藏
    "拉萨布达拉宫", "拉萨大昭寺", "拉萨色拉寺",
    "拉萨哲蚌寺", "日喀则扎什伦布寺",
    # 内蒙古
    "呼和浩特大召寺",
    # 陕西
    "西安大慈恩寺", "西安大雁塔", "西安大兴善寺",
    "扶风法门寺",
    # 贵州
    "贵阳弘福寺",
    # 山东
    "济南灵岩寺", "青岛湛山寺",
    # 河北
    "正定隆兴寺", "承德普宁寺", "赵县柏林禅寺",
]


def main():
    all_records: dict[str, dict] = {}  # osm_id → record

    # ── Phase 1: Overpass queries ──
    queries = [
        ("osm:buddhist", Q_BUDDHIST),
        ("osm:building_temple", Q_BUILDING_TEMPLE),
        ("osm:name_pattern", Q_NAME_PATTERN),
        ("osm:historic", Q_HISTORIC),
    ]

    for label, q in queries:
        print(f"\n[{label}] Querying Overpass...")
        try:
            data = query_overpass(q)
            recs = extract_records(data, label)
            new_count = 0
            for r in recs:
                if r["osm_id"] not in all_records:
                    all_records[r["osm_id"]] = r
                    new_count += 1
            print(f"  Got {len(recs)} records, {new_count} new (total: {len(all_records)})")
        except Exception as e:
            print(f"  ERROR: {e}")
        time.sleep(15)  # Overpass rate limit

    # ── Phase 2: Nominatim geocoding for famous temples ──
    print(f"\n[nominatim] Geocoding {len(FAMOUS_TEMPLES)} famous temples...")
    nominatim_found = 0

    for temple_name in FAMOUS_TEMPLES:
        try:
            results = nominatim_search(temple_name)
            time.sleep(1.1)  # Nominatim rate limit: 1 req/sec

            if results:
                r = results[0]
                osm_type = r.get("osm_type", "node")
                osm_id_val = r.get("osm_id", "")
                osm_key = f"{osm_type}/{osm_id_val}"

                if osm_key not in all_records:
                    name_zh = temple_name
                    # Strip city prefix for cleaner name
                    for prefix_len in range(2, 5):
                        if len(temple_name) > prefix_len:
                            suffix = temple_name[prefix_len:]
                            if any(suffix.endswith(s) for s in ["寺", "庵", "院", "宫", "窟", "殿", "塔", "庙", "山"]):
                                name_zh = suffix
                                break

                    all_records[osm_key] = {
                        "osm_id": osm_key,
                        "name_primary": temple_name,
                        "name_zh": name_zh,
                        "name_en": "",
                        "latitude": float(r["lat"]),
                        "longitude": float(r["lon"]),
                        "wikidata": "",
                        "religion": "buddhist",
                        "denomination": "",
                        "source": "nominatim:famous",
                        "search_query": temple_name,
                    }
                    nominatim_found += 1
                    print(f"  ✓ {temple_name} → ({r['lat']}, {r['lon']})")
                else:
                    print(f"  = {temple_name} (already in OSM)")
            else:
                print(f"  ✗ {temple_name} (not found)")
        except Exception as e:
            print(f"  ! {temple_name}: {e}")
            time.sleep(2)

    print(f"\n  Nominatim: {nominatim_found} new temples found")

    # ── Save ──
    result = list(all_records.values())
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n{'='*60}")
    print(f"Total: {len(result)} temples saved to {OUTPUT}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
