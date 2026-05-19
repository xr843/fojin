"""
Scrape Buddhist temples from Chinese Wikipedia (via Wikidata SPARQL).

Strategy:
1. Query Wikidata SPARQL for all Buddhist temples/monasteries/stupas with
   (a) a Chinese Wikipedia sitelink, and (b) P625 coordinates.
2. Pull rich structured metadata in one go: inception date, religion/denomination
   (P140), located-in-country (P17), located administrative entity (P131),
   English/Chinese/Japanese labels, Wikidata Q-ID.
3. For each result, also fetch the Wikipedia infobox wikitext to extract the
   dynasty string (maps Chinese dynasty names from inception year as fallback).
4. Write to /home/lqsxi/projects/fojin/backend/data/wikipedia_temples.json

Usage:
    cd backend
    python3 scripts/scrape_wikipedia_temples.py
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
WIKIPEDIA_API_URL = "https://zh.wikipedia.org/w/api.php"
USER_AGENT = "FoJinBot/1.0 (https://fojin.app; Buddhist digital humanities)"

OUTPUT_PATH = "/home/lqsxi/projects/fojin/backend/data/wikipedia_temples.json"

# Types of Buddhist structures to include (Q-IDs of P31/P279* roots).
# Each entry: (qid, label, require_buddhism_filter)
# For broad types (cave, shrine), we require P140=Buddhism to avoid secular sites.
# NOTE: we do not use this list for Wikidata queries anymore — we query by
# P140=Buddhism directly (definitional criterion). See build_sparql_query().
BUDDHIST_TYPES: list[tuple[str, str, bool]] = []

# Q140 = Buddhism (religion)
BUDDHISM_QID = "Q748"


# -------------------- Dynasty mapping --------------------
# Maps a founding year (Gregorian, negative = BCE) to Chinese dynasty string.
# These are simplified bounds covering the dominant dynasty at a given year.
DYNASTY_RANGES: list[tuple[int, int, str]] = [
    (-2070, -1600, "夏"),
    (-1600, -1046, "商"),
    (-1046, -771, "西周"),
    (-770, -476, "春秋"),
    (-475, -221, "战国"),
    (-221, -206, "秦"),
    (-206, 9, "西汉"),
    (9, 25, "新莽"),
    (25, 220, "东汉"),
    (220, 265, "三国"),
    (265, 317, "西晋"),
    (317, 420, "东晋"),
    (420, 589, "南北朝"),
    (581, 618, "隋"),
    (618, 907, "唐"),
    (907, 960, "五代十国"),
    (960, 1127, "北宋"),
    (1127, 1279, "南宋"),
    (1271, 1368, "元"),
    (1368, 1644, "明"),
    (1636, 1912, "清"),
    (1912, 1949, "民国"),
    (1949, 9999, "现代"),
]


JAPAN_ERA_RANGES: list[tuple[int, int, str]] = [
    (-10000, 538, "日本古坟时代"),
    (538, 710, "日本飞鸟时代"),
    (710, 794, "日本奈良时代"),
    (794, 1185, "日本平安时代"),
    (1185, 1333, "日本镰仓时代"),
    (1336, 1573, "日本室町时代"),
    (1573, 1603, "日本安土桃山时代"),
    (1603, 1868, "日本江户时代"),
    (1868, 1912, "日本明治时代"),
    (1912, 1926, "日本大正时代"),
    (1926, 1989, "日本昭和时代"),
    (1989, 2019, "日本平成时代"),
    (2019, 9999, "日本令和时代"),
]

KOREA_ERA_RANGES: list[tuple[int, int, str]] = [
    (-10000, 668, "三国时代"),
    (668, 935, "统一新罗"),
    (918, 1392, "高丽"),
    (1392, 1897, "朝鲜王朝"),
    (1897, 1910, "大韩帝国"),
    (1910, 1945, "日本殖民时期"),
    (1945, 9999, "现代"),
]

CHINA_ALIASES = {"中国", "中华人民共和国", "China", "台湾", "中華民國", "西藏", "清朝", "新罗", "高丽", "高句丽", "琉球國"}
JAPAN_ALIASES = {"日本"}
KOREA_ALIASES = {"韩国", "朝鮮民主主義人民共和國", "朝鲜王朝", "大韩民国", "朝鲜"}


def year_to_dynasty(year: int | None, country: str | None) -> str | None:
    if year is None:
        return None
    if country in JAPAN_ALIASES:
        ranges = JAPAN_ERA_RANGES
    elif country in KOREA_ALIASES:
        ranges = KOREA_ERA_RANGES
    elif country in CHINA_ALIASES or country is None:
        ranges = DYNASTY_RANGES
    else:
        return None
    for start, end, name in ranges:
        if start <= year <= end:
            return name
    return None


# -------------------- HTTP helpers --------------------

def http_get(url: str, params: dict, accept: str = "application/sparql-results+json") -> dict:
    qs = urllib.parse.urlencode(params)
    full = f"{url}?{qs}"
    req = urllib.request.Request(
        full,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


# -------------------- SPARQL query --------------------

def build_sparql_query_by_religion() -> str:
    # Definitional query: P140 (religion) = Buddhism (or any subtype), has
    # coords, has zh.wikipedia sitelink. Item must be an instance-of a
    # building/place/structure (not a kingdom/state/person).
    return f"""
SELECT ?item ?sitelink ?coord ?inception ?country ?admin ?religion ?denomination ?typeClass
       ?itemLabelZh ?itemLabelEn ?itemLabelJa
       ?countryLabelZh ?adminLabelZh ?religionLabelZh ?denominationLabelZh ?typeLabelZh
WHERE {{
  ?item wdt:P140/wdt:P279* wd:{BUDDHISM_QID} .
  ?item wdt:P625 ?coord .
  ?item wdt:P31 ?typeClass .
  ?typeClass wdt:P279* ?rootStructure .
  VALUES ?rootStructure {{
    wd:Q41176         # building
    wd:Q811979        # architectural structure
    wd:Q1370598       # place of worship
    wd:Q15243209      # historic site
    wd:Q839954        # archaeological site
    wd:Q178561        # stupa (self)
    wd:Q5393308       # buddhist temple (self)
    wd:Q160742        # buddhist monastery (self)
  }}
  ?sitelink schema:isPartOf <https://zh.wikipedia.org/> ;
            schema:about ?item .
  OPTIONAL {{ ?item wdt:P571 ?inception . }}
  OPTIONAL {{
    ?item wdt:P31 ?typeClass .
    OPTIONAL {{ ?typeClass rdfs:label ?typeLabelZh FILTER(LANG(?typeLabelZh)="zh") }}
  }}
  OPTIONAL {{
    ?item wdt:P17 ?country .
    OPTIONAL {{ ?country rdfs:label ?countryLabelZh FILTER(LANG(?countryLabelZh)="zh") }}
  }}
  OPTIONAL {{
    ?item wdt:P131 ?admin .
    OPTIONAL {{ ?admin rdfs:label ?adminLabelZh FILTER(LANG(?adminLabelZh)="zh") }}
  }}
  OPTIONAL {{
    ?item wdt:P140 ?religion .
    OPTIONAL {{ ?religion rdfs:label ?religionLabelZh FILTER(LANG(?religionLabelZh)="zh") }}
  }}
  OPTIONAL {{
    ?item wdt:P1049 ?denomination .
    OPTIONAL {{ ?denomination rdfs:label ?denominationLabelZh FILTER(LANG(?denominationLabelZh)="zh") }}
  }}
  OPTIONAL {{ ?item rdfs:label ?itemLabelZh FILTER(LANG(?itemLabelZh)="zh") }}
  OPTIONAL {{ ?item rdfs:label ?itemLabelEn FILTER(LANG(?itemLabelEn)="en") }}
  OPTIONAL {{ ?item rdfs:label ?itemLabelJa FILTER(LANG(?itemLabelJa)="ja") }}
}}
"""


def build_sparql_query_by_type(type_qid: str) -> str:
    # Strict P31 match (no P279 traversal) — only direct instance-of.
    # Also exclude items whose P140 religion is a known non-Buddhist one
    # (Q160742 "Buddhist monastery" is abused by editors for Christian abbeys).
    return f"""
SELECT ?item ?sitelink ?coord ?inception ?country ?admin ?religion ?denomination ?typeClass
       ?itemLabelZh ?itemLabelEn ?itemLabelJa
       ?countryLabelZh ?adminLabelZh ?religionLabelZh ?denominationLabelZh ?typeLabelZh
WHERE {{
  ?item wdt:P31 wd:{type_qid} .
  BIND(wd:{type_qid} AS ?typeClass)
  # Must either have P140=Buddhism, OR have no P140 set at all.
  FILTER NOT EXISTS {{
    ?item wdt:P140 ?r .
    FILTER NOT EXISTS {{ ?r wdt:P279* wd:{BUDDHISM_QID} }}
  }}
  ?item wdt:P625 ?coord .
  ?sitelink schema:isPartOf <https://zh.wikipedia.org/> ;
            schema:about ?item .
  OPTIONAL {{ ?item wdt:P571 ?inception . }}
  OPTIONAL {{
    ?item wdt:P17 ?country .
    OPTIONAL {{ ?country rdfs:label ?countryLabelZh FILTER(LANG(?countryLabelZh)="zh") }}
  }}
  OPTIONAL {{
    ?item wdt:P131 ?admin .
    OPTIONAL {{ ?admin rdfs:label ?adminLabelZh FILTER(LANG(?adminLabelZh)="zh") }}
  }}
  OPTIONAL {{
    ?item wdt:P140 ?religion .
    OPTIONAL {{ ?religion rdfs:label ?religionLabelZh FILTER(LANG(?religionLabelZh)="zh") }}
  }}
  OPTIONAL {{
    ?item wdt:P1049 ?denomination .
    OPTIONAL {{ ?denomination rdfs:label ?denominationLabelZh FILTER(LANG(?denominationLabelZh)="zh") }}
  }}
  OPTIONAL {{ ?typeClass rdfs:label ?typeLabelZh FILTER(LANG(?typeLabelZh)="zh") }}
  OPTIONAL {{ ?item rdfs:label ?itemLabelZh FILTER(LANG(?itemLabelZh)="zh") }}
  OPTIONAL {{ ?item rdfs:label ?itemLabelEn FILTER(LANG(?itemLabelEn)="en") }}
  OPTIONAL {{ ?item rdfs:label ?itemLabelJa FILTER(LANG(?itemLabelJa)="ja") }}
}}
"""


# Buddhist-specific P31 types (strict, no subclass traversal).
STRICT_BUDDHIST_TYPES = [
    ("Q5393308", "Buddhist temple"),
    ("Q160742",  "Buddhist monastery"),
    ("Q843724",  "vihara"),
    ("Q1349929", "Tibetan Buddhist monastery"),
    ("Q26721702", "Thai Buddhist temple"),
    ("Q1219736", "Hindu temple"),  # not used, placeholder to avoid
]
# remove non-buddhist
STRICT_BUDDHIST_TYPES = [t for t in STRICT_BUDDHIST_TYPES if "Hindu" not in t[1]]


def run_sparql_once(query: str, retries: int = 3) -> list[dict]:
    for attempt in range(1, retries + 1):
        try:
            data = http_get(WIKIDATA_SPARQL_URL, {"query": query, "format": "json"})
            return data.get("results", {}).get("bindings", [])
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:200]
            print(f"[sparql] HTTP {e.code} (attempt {attempt}/{retries}): {body}", flush=True)
            if attempt == retries:
                return []
            time.sleep(10 * attempt)
        except Exception as e:
            print(f"[sparql] {e} (attempt {attempt}/{retries})", flush=True)
            if attempt == retries:
                return []
            time.sleep(10 * attempt)
    return []


def run_sparql(retries: int = 3) -> list[dict]:
    all_rows: list[dict] = []
    # Query 1: by religion = Buddhism
    query = build_sparql_query_by_religion()
    print("[sparql] querying Wikidata: religion=Buddhism + zh sitelink + coord", flush=True)
    rows = run_sparql_once(query, retries=retries)
    print(f"[sparql] religion query: {len(rows)} rows", flush=True)
    all_rows.extend(rows)
    time.sleep(2)

    # Query 2: strict P31 type queries (no P279 traversal) to catch temples
    # that don't have P140 set but are clearly Buddhist by type.
    for qid, label in STRICT_BUDDHIST_TYPES:
        q = build_sparql_query_by_type(qid)
        rows = run_sparql_once(q, retries=retries)
        print(f"[sparql] type {qid} ({label}): {len(rows)} rows", flush=True)
        all_rows.extend(rows)
        time.sleep(2)

    return all_rows


# -------------------- Parsing helpers --------------------

POINT_RE = re.compile(r"Point\(([-0-9.]+)\s+([-0-9.]+)\)")

def parse_point(pt: str) -> tuple[float, float] | None:
    m = POINT_RE.match(pt.strip())
    if not m:
        return None
    lon, lat = float(m.group(1)), float(m.group(2))
    return lat, lon


def parse_inception(s: str) -> int | None:
    # "+0618-01-01T00:00:00Z" or "-0221-01-01T00:00:00Z"
    if not s:
        return None
    m = re.match(r"([+-]?)(\d{1,5})-", s)
    if not m:
        return None
    sign, year = m.group(1), int(m.group(2))
    if sign == "-":
        year = -year
    return year


def extract_qid(uri: str) -> str | None:
    if not uri:
        return None
    m = re.search(r"/(Q\d+)$", uri)
    return m.group(1) if m else None


def get_val(row: dict, key: str) -> str | None:
    v = row.get(key)
    if not v:
        return None
    return v.get("value")


def extract_wikipedia_title(sitelink: str) -> str | None:
    # https://zh.wikipedia.org/wiki/XXX
    if not sitelink:
        return None
    prefix = "https://zh.wikipedia.org/wiki/"
    if sitelink.startswith(prefix):
        raw = sitelink[len(prefix):]
        return urllib.parse.unquote(raw).replace("_", " ")
    return None


# -------------------- Country normalization --------------------

COUNTRY_ZH = {
    # Common country labels from Wikidata zh service
    "中华人民共和国": "中国",
    "中国": "中国",
    "日本": "日本",
    "大韩民国": "韩国",
    "韩国": "韩国",
    "朝鲜民主主义人民共和国": "朝鲜",
    "越南": "越南",
    "印度": "印度",
    "斯里兰卡": "斯里兰卡",
    "缅甸": "缅甸",
    "泰国": "泰国",
    "柬埔寨": "柬埔寨",
    "寮国": "老挝",
    "老挝": "老挝",
    "不丹": "不丹",
    "尼泊尔": "尼泊尔",
    "蒙古": "蒙古",
    "蒙古国": "蒙古",
    "中华民国": "台湾",
    "台湾": "台湾",
    "新加坡": "新加坡",
    "马来西亚": "马来西亚",
    "印度尼西亚": "印度尼西亚",
}


def normalize_country(raw: str | None) -> str | None:
    if not raw:
        return None
    return COUNTRY_ZH.get(raw, raw)


# -------------------- Denomination/school normalization --------------------

SCHOOL_KEYWORDS = [
    ("禅宗", "禅宗"),
    ("净土", "净土宗"),
    ("淨土", "净土宗"),
    ("天台", "天台宗"),
    ("华严", "华严宗"),
    ("華嚴", "华严宗"),
    ("律宗", "律宗"),
    ("律", "律宗"),
    ("密宗", "密宗"),
    ("密教", "密宗"),
    ("真言", "真言宗"),
    ("唯识", "唯识宗"),
    ("三论", "三论宗"),
    ("三論", "三论宗"),
    ("藏传", "藏传佛教"),
    ("藏傳", "藏传佛教"),
    ("格鲁", "格鲁派"),
    ("格魯", "格鲁派"),
    ("噶举", "噶举派"),
    ("噶舉", "噶举派"),
    ("宁玛", "宁玛派"),
    ("寧瑪", "宁玛派"),
    ("萨迦", "萨迦派"),
    ("薩迦", "萨迦派"),
    ("上座部", "上座部佛教"),
    ("南传", "上座部佛教"),
    ("南傳", "上座部佛教"),
    ("Theravada", "上座部佛教"),
    ("曹洞", "曹洞宗"),
    ("临济", "临济宗"),
    ("臨濟", "临济宗"),
    ("黄檗", "黄檗宗"),
    ("黃檗", "黄檗宗"),
    ("日莲", "日莲宗"),
    ("日蓮", "日莲宗"),
]


def normalize_school(raw: str | None) -> str | None:
    if not raw:
        return None
    for key, canon in SCHOOL_KEYWORDS:
        if key.lower() in raw.lower():
            return canon
    return raw  # keep raw if no mapping


# -------------------- Main transform --------------------

# Heuristic: names/descriptions containing these tokens indicate non-Buddhist.
CHRISTIAN_TOKENS = [
    "Abbey", "abbey", "Priory", "priory", "Cathedral", "cathedral",
    "Church", "church", "chapelle", "Chapelle", "église", "Église",
    "Abbaye", "abbaye", "Basilica", "basilica", "Cloister", "cloister",
    "Monastery of Saint", "Saint-", "Notre-Dame", "St.", "Kloster",
    "monastery",  # english 'monastery' without 'Buddhist' qualifier
]
CHRISTIAN_ZH_TOKENS = [
    "天主教", "基督教", "聖公", "圣公", "东正教", "東正教",
    "主教座堂", "大教堂", "教堂", "修道院", "修院",
]


def looks_christian(name_zh: str | None, name_en: str | None) -> bool:
    # zh name: "修道院"/"教堂" without any Buddhist marker
    if name_zh:
        has_christian = any(t in name_zh for t in CHRISTIAN_ZH_TOKENS)
        has_buddhist = any(t in name_zh for t in ("寺", "院", "庙", "廟", "塔", "禅", "禪", "精舍", "菩提", "伽蓝", "伽藍", "禪寺", "禪林", "佛", "法华", "法華", "兰若", "蘭若"))
        # "修道院"/"教堂" alone (without Buddhist marker) -> christian
        if has_christian and not has_buddhist:
            # allow Japanese/Korean "院" which also used in Christian contexts,
            # but we already marked 教堂/修道院 as Christian
            return True
    if name_en:
        if any(t in name_en for t in CHRISTIAN_TOKENS):
            # BUT: if name_en also contains "Buddhist" / "Temple" / "Pagoda" / "Vihara", keep
            en_lower = name_en.lower()
            buddhist_whitelist = (
                "buddhist", "temple", "pagoda", "vihara", "stupa", "zen",
                "shaolin", "dharma", "nalanda", "tibetan", "tibet", "tantra",
                "kagyu", "nyingma", "sakya", "gelug", "vajra", "thiền",
                "chùa", "chua", "wat ", "theravada", "mahayana", "sangha",
                "karma kagyu", "lama", "rinpoche", "gompa",
            )
            if not any(t in en_lower for t in buddhist_whitelist):
                return True
    return False


def transform_rows(rows: list[dict]) -> list[dict]:
    # Multiple rows can exist per item (different P131 admins, etc). Merge.
    by_qid: dict[str, dict] = {}
    for row in rows:
        qid = extract_qid(get_val(row, "item") or "")
        if not qid:
            continue
        coord = parse_point(get_val(row, "coord") or "")
        if not coord:
            continue
        lat, lon = coord

        sitelink = get_val(row, "sitelink")
        title = extract_wikipedia_title(sitelink or "")

        inception_raw = get_val(row, "inception")
        year = parse_inception(inception_raw or "")

        country = normalize_country(get_val(row, "countryLabelZh"))
        admin = get_val(row, "adminLabelZh")
        religion = get_val(row, "religionLabelZh")
        denomination = get_val(row, "denominationLabelZh")
        school = normalize_school(denomination) or normalize_school(religion)

        name_zh = get_val(row, "itemLabelZh")
        name_en = get_val(row, "itemLabelEn")
        name_ja = get_val(row, "itemLabelJa")
        # zh label may fall back to Q-ID; drop if that's the case
        if name_zh and name_zh.startswith("Q") and name_zh[1:].isdigit():
            name_zh = title  # use the sitelink title as zh name

        # Filter out obvious Christian misclassifications
        if looks_christian(name_zh or title, name_en):
            continue

        existing = by_qid.get(qid)
        if existing is None:
            by_qid[qid] = {
                "wikidata_id": qid,
                "wikipedia_title": title,
                "wikipedia_url": sitelink,
                "name_zh": name_zh or title,
                "name_en": name_en,
                "name_ja": name_ja,
                "latitude": lat,
                "longitude": lon,
                "country": country,
                "province": admin,
                "year_founded": year,
                "dynasty": year_to_dynasty(year, country),
                "school": school,
            }
        else:
            # Merge: prefer non-null values; collect all province candidates
            if not existing.get("province") and admin:
                existing["province"] = admin
            if not existing.get("school") and school:
                existing["school"] = school
            if not existing.get("name_en") and name_en:
                existing["name_en"] = name_en
            if not existing.get("name_ja") and name_ja:
                existing["name_ja"] = name_ja
            if existing.get("year_founded") is None and year is not None:
                existing["year_founded"] = year
                existing["dynasty"] = year_to_dynasty(year, existing.get("country"))

    return list(by_qid.values())


# -------------------- Stats --------------------

def print_stats(records: list[dict]) -> None:
    total = len(records)
    with_dynasty = sum(1 for r in records if r.get("dynasty"))
    with_year = sum(1 for r in records if r.get("year_founded") is not None)
    with_school = sum(1 for r in records if r.get("school"))
    with_en = sum(1 for r in records if r.get("name_en"))
    with_ja = sum(1 for r in records if r.get("name_ja"))

    by_country: dict[str, int] = {}
    for r in records:
        c = r.get("country") or "(未知)"
        by_country[c] = by_country.get(c, 0) + 1

    print(f"\n=== Wikipedia Buddhist Temples ===")
    print(f"Total records:        {total}")
    print(f"With year_founded:    {with_year}  ({100*with_year/total:.1f}%)")
    print(f"With dynasty:         {with_dynasty}  ({100*with_dynasty/total:.1f}%)")
    print(f"With school:          {with_school}  ({100*with_school/total:.1f}%)")
    print(f"With name_en:         {with_en}")
    print(f"With name_ja:         {with_ja}")
    print(f"\nBy country:")
    for c, n in sorted(by_country.items(), key=lambda x: -x[1]):
        print(f"  {c:20s} {n}")


# -------------------- Main --------------------

def main() -> None:
    rows = run_sparql()
    records = transform_rows(rows)
    # Sort by country then name
    records.sort(key=lambda r: (r.get("country") or "", r.get("name_zh") or ""))

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print_stats(records)
    print(f"\nSaved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
