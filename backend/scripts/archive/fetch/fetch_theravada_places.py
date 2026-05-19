"""
Fetch Theravada / Pali-canon places from Wikidata.

Two phases:
  A. Canonical Nikaya places — hand-curated Q-IDs (祇园精舍、竹林精舍、
     舍卫城、王舍城、吠舍离、迦毗罗卫、拘尸那罗、鹿野苑、那烂陀、桑奇、
     米欣特莱、阿努拉德普勒、波隆纳鲁沃、康提、仰光大金塔、蒲甘、吴哥窟、
     素可泰、阿育他耶、柏威夏 等)。
  B. Regional SPARQL sweep — monasteries (Q160742), Buddhist temples
     (Q5393308), stupas (Q178561), pagodas (Q199451) in Sri Lanka,
     Myanmar, Thailand, Cambodia, Laos, India, Nepal, Bangladesh; plus
     Khmer temples (Q10373548).

Output: data/suttacentral_places.json

Run from a machine with internet (Wikidata SPARQL is rate-limited from
some VPS IPs). Then copy JSON to server.
"""
import json
import time
import urllib.parse
import urllib.request

USER_AGENT = "FoJinBot/1.0 (https://fojin.app; Buddhist studies platform)"
SPARQL_URL = "https://query.wikidata.org/sparql"
OUTPUT = "data/suttacentral_places.json"

# Verified Q-IDs for canonical Nikaya / Theravada pilgrimage places
NIKAYA_QIDS: dict[str, tuple[str, str]] = {
    # qid -> (English hint, curated Chinese name)
    "Q863683":   ("Rajgir",                       "王舍城"),
    "Q176767":   ("Bodh Gaya",                    "菩提伽耶"),
    "Q324394":   ("Sarnath",                      "鹿野苑"),
    "Q9213":     ("Lumbini",                      "蓝毗尼"),
    "Q955882":   ("Kapilvastu (Nepal)",           "迦毗罗卫"),
    "Q825673":   ("Kushinagar",                   "拘尸那罗"),
    "Q2594448":  ("Shravasti (Saheth-Maheth)",    "舍卫城"),
    "Q80484":    ("Patna / Pataliputra",          "华氏城"),
    "Q30587895": ("Kesaria stupa",                "吉舍梨大塔"),
    "Q181123":   ("Sanchi",                       "桑奇"),
    "Q79980":    ("Varanasi",                     "波罗奈"),
    "Q864810":   ("Sankassa",                     "僧伽施"),
    "Q749108":   ("Nagarjunakonda",               "龙树山"),
    "Q305242":   ("Jetavana",                     "祇树给孤独园"),
    "Q17031293": ("Venuvana",                     "竹林精舍"),
    "Q4513":     ("Mahabodhi Temple",             "大菩提寺"),
    "Q184427":   ("Ajanta Caves",                 "阿旃陀石窟"),
    "Q189616":   ("Ellora Caves",                 "埃洛拉石窟"),
    "Q216243":   ("Nalanda Mahavihara",           "那烂陀寺"),
    "Q1985137":  ("Dhamek Stupa",                 "达麦克塔"),
    "Q3389059":  ("Piprahwa",                     "毗卢婆"),
    # Sri Lanka
    "Q5724":     ("Anuradhapura",                 "阿努拉德普勒"),
    "Q394443":   ("Polonnaruwa",                  "波隆纳鲁沃"),
    "Q203197":   ("Kandy",                        "康提"),
    "Q289175":   ("Temple of the Tooth",          "佛牙寺"),
    "Q1478212":  ("Mihintale",                    "米欣特莱"),
    "Q320543":   ("Abhayagiri vihāra",            "无畏山寺"),
    "Q542107":   ("Mahavihara of Anuradhapura",   "大寺（阿努拉德普勒）"),
    "Q1961579":  ("Jetavanaramaya",               "祇陀林寺（锡兰）"),
    "Q944175":   ("Sri Maha Bodhi",               "摩诃菩提树（锡兰）"),
    "Q3534755":  ("Ruwanwelisaya",                "鲁梵伐利塔"),
    "Q7799227":  ("Thuparamaya",                  "图帕兰马亚塔"),
    "Q3610571":  ("Isurumuniya",                  "伊苏鲁穆尼亚寺"),
    "Q3217592":  ("Lankatilaka Vihara",           "兰卡提拉卡寺"),
    "Q5521071":  ("Gangaramaya Temple",           "冈嘎拉玛寺"),
    "Q3610575":  ("Kelaniya Raja Maha Vihara",    "凯拉尼亚大寺"),
    # Myanmar
    "Q464535":   ("Shwedagon Pagoda",             "仰光大金塔"),
    "Q13069237": ("Old Bagan",                    "蒲甘古城"),
    "Q37995":    ("Yangon",                       "仰光"),
    "Q485727":   ("Ananda Temple",                "阿难陀寺（蒲甘）"),
    "Q2747222":  ("Shwezigon Pagoda",             "瑞喜宫塔"),
    "Q1207545":  ("Dhammayangyi Temple",          "达摩央吉寺"),
    # Thailand
    "Q1025100":  ("Ayutthaya Historical Park",    "阿育他耶历史公园"),
    "Q423654":   ("Sukhothai Historical Park",    "素可泰历史公园"),
    "Q1045876":  ("Wat Phra Kaew",                "玉佛寺"),
    "Q724970":   ("Wat Arun",                     "郑王庙"),
    "Q1059910":  ("Wat Pho",                      "卧佛寺"),
    "Q2552296":  ("Wat Mahathat Sukhothai",       "玛哈泰寺（素可泰）"),
    "Q2063779":  ("Wat Chaiwatthanaram",          "柴瓦塔那兰寺"),
    # Cambodia
    "Q43473":    ("Angkor Wat",                   "吴哥窟"),
    "Q790099":   ("Banteay Srei",                 "女王宫"),
    "Q592846":   ("Ta Prohm",                     "塔布隆寺"),
    "Q45949":    ("Preah Vihear Temple",          "柏威夏寺"),
}

# Country Q-IDs for regional sweep (Theravada heartland + Buddhist S. Asia)
COUNTRIES = {
    "LK": "Q854", "MM": "Q836", "TH": "Q869", "KH": "Q424",
    "LA": "Q819", "IN": "Q668", "NP": "Q837", "BD": "Q902",
}

EXPECTED_COUNTRIES = {
    "India", "Nepal", "Sri Lanka", "Myanmar", "Thailand",
    "Cambodia", "Laos", "Bangladesh", "Bhutan",
}


def sparql(q: str) -> list[dict]:
    url = SPARQL_URL + "?" + urllib.parse.urlencode({"query": q, "format": "json"})
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/sparql-results+json",
    })
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read()).get("results", {}).get("bindings", [])


def parse_point(s: str) -> tuple[float, float] | None:
    if not s.startswith("Point("):
        return None
    try:
        lng, lat = s[6:-1].split()
        return float(lat), float(lng)
    except Exception:
        return None


def fetch_canonical() -> list[dict]:
    values = " ".join(f"wd:{q}" for q in NIKAYA_QIDS)
    query = f"""
SELECT ?item ?itemLabel ?itemLabelZh ?itemLabelPi ?itemLabelSa ?coord ?desc ?countryLabel WHERE {{
  VALUES ?item {{ {values} }}
  ?item wdt:P625 ?coord .
  OPTIONAL {{ ?item wdt:P17 ?country . }}
  OPTIONAL {{ ?item rdfs:label ?itemLabelZh FILTER(LANG(?itemLabelZh) = "zh") }}
  OPTIONAL {{ ?item rdfs:label ?itemLabelPi FILTER(LANG(?itemLabelPi) = "pi") }}
  OPTIONAL {{ ?item rdfs:label ?itemLabelSa FILTER(LANG(?itemLabelSa) = "sa") }}
  OPTIONAL {{ ?item schema:description ?desc FILTER(LANG(?desc) = "zh") }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
}}
"""
    bindings = sparql(query)
    out = []
    seen = set()
    for r in bindings:
        qid = r.get("item", {}).get("value", "").split("/")[-1]
        if qid in seen:
            continue
        coord = parse_point(r.get("coord", {}).get("value", ""))
        if not coord:
            continue
        country = r.get("countryLabel", {}).get("value", "")
        if country and country not in EXPECTED_COUNTRIES:
            # sanity check — reject Q-IDs that resolved to wrong place
            continue
        name_en_wd = r.get("itemLabel", {}).get("value", "")
        if name_en_wd.startswith("Q") and name_en_wd[1:].isdigit():
            name_en_wd = ""
        en_hint, zh_curated = NIKAYA_QIDS[qid]
        seen.add(qid)
        out.append({
            "wikidata_id": qid,
            "name_en": name_en_wd or en_hint,
            "name_zh": zh_curated,
            "name_pi": r.get("itemLabelPi", {}).get("value", ""),
            "name_sa": r.get("itemLabelSa", {}).get("value", ""),
            "description": r.get("desc", {}).get("value", ""),
            "latitude": coord[0],
            "longitude": coord[1],
            "country": country,
            "source": "wikidata:nikaya_canonical",
        })
    return out


def fetch_region(country_qid: str) -> list[dict]:
    query = f"""
SELECT ?item ?itemLabel ?itemLabelZh ?coord WHERE {{
  ?item wdt:P17 wd:{country_qid} .
  ?item wdt:P625 ?coord .
  {{ ?item wdt:P31/wdt:P279* wd:Q160742 . }}
  UNION {{ ?item wdt:P31/wdt:P279* wd:Q5393308 . }}
  UNION {{ ?item wdt:P31/wdt:P279* wd:Q178561 . }}
  UNION {{ ?item wdt:P31/wdt:P279* wd:Q199451 . }}
  UNION {{ ?item wdt:P31/wdt:P279* wd:Q10373548 . }}
  OPTIONAL {{ ?item rdfs:label ?itemLabelZh FILTER(LANG(?itemLabelZh) = "zh") }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
}} LIMIT 600
"""
    bindings = sparql(query)
    out = []
    seen = set()
    for r in bindings:
        qid = r.get("item", {}).get("value", "").split("/")[-1]
        if qid in seen:
            continue
        coord = parse_point(r.get("coord", {}).get("value", ""))
        if not coord:
            continue
        name_en = r.get("itemLabel", {}).get("value", "")
        name_zh = r.get("itemLabelZh", {}).get("value", "")
        if name_en.startswith("Q") and name_en[1:].isdigit():
            name_en = ""
        if not name_en and not name_zh:
            continue
        seen.add(qid)
        out.append({
            "wikidata_id": qid,
            "name_en": name_en,
            "name_zh": name_zh,
            "name_pi": "",
            "name_sa": "",
            "description": "",
            "latitude": coord[0],
            "longitude": coord[1],
            "country": country_qid,
            "source": "wikidata:theravada_region",
        })
    return out


def main() -> None:
    print("Fetching canonical Nikaya places...")
    canonical = fetch_canonical()
    print(f"  got {len(canonical)} canonical records")

    by_qid: dict[str, dict] = {r["wikidata_id"]: r for r in canonical}

    for cc, qid in COUNTRIES.items():
        print(f"Fetching regional places for {cc} ({qid})...")
        try:
            regional = fetch_region(qid)
            new = 0
            for r in regional:
                if r["wikidata_id"] not in by_qid:
                    by_qid[r["wikidata_id"]] = r
                    new += 1
            print(f"  +{new} new (total {len(by_qid)})")
        except Exception as e:
            print(f"  ERROR: {e}")
        time.sleep(2)

    final = list(by_qid.values())
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(final)} places to {OUTPUT}")


if __name__ == "__main__":
    main()
