"""Fetch additional Buddhist persons from Wikidata using broader SPARQL queries.

Complements data/buddhist_persons.json (which mainly uses birth place P19) by
adding persons with:
  - work location (P937)
  - place of burial (P119)
  - residence (P551)
  - sect founder (P112)
  - translator occupation

Run locally to avoid server IP rate-limiting.

Output: data/wikidata_persons_extended.json
"""
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
USER_AGENT = "FoJinBot/1.0 (https://fojin.app; Buddhist studies platform)"
BACKEND_DIR = Path(__file__).resolve().parents[1]
EXISTING_PATH = BACKEND_DIR / "data" / "buddhist_persons.json"
DESC_PATH = BACKEND_DIR / "data" / "person_descriptions.json"
OUTPUT_PATH = BACKEND_DIR / "data" / "wikidata_persons_extended.json"

# -----------------------------------------------------------------------------
# SPARQL queries
# -----------------------------------------------------------------------------
BUDDHIST_CLERGY_UNION = """
  { ?item wdt:P106/wdt:P279* wd:Q4263842 . }
  UNION { ?item wdt:P106/wdt:P279* wd:Q1662844 . }
  UNION { ?item wdt:P106 wd:Q161598 . }
  UNION { ?item wdt:P106 wd:Q3336976 . }
  UNION { ?item wdt:P106 wd:Q208974 . }
"""


def build_place_query(place_prop: str) -> str:
    return f"""
SELECT ?item ?itemLabel ?zhLabel ?jaLabel ?coord ?placeLabel ?birthYear ?deathYear WHERE {{
  {BUDDHIST_CLERGY_UNION}
  ?item wdt:{place_prop} ?place .
  ?place wdt:P625 ?coord .
  OPTIONAL {{ ?item wdt:P569 ?birth . BIND(YEAR(?birth) AS ?birthYear) }}
  OPTIONAL {{ ?item wdt:P570 ?death . BIND(YEAR(?death) AS ?deathYear) }}
  OPTIONAL {{ ?item rdfs:label ?zhLabel FILTER(LANG(?zhLabel) = "zh") }}
  OPTIONAL {{ ?item rdfs:label ?jaLabel FILTER(LANG(?jaLabel) = "ja") }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . ?item rdfs:label ?itemLabel . ?place rdfs:label ?placeLabel . }}
}} LIMIT 5000
"""


FOUNDER_QUERY = """
SELECT DISTINCT ?item ?itemLabel ?zhLabel ?jaLabel ?coord ?placeLabel ?birthYear ?deathYear WHERE {
  ?sect wdt:P112 ?item .
  { ?sect wdt:P31/wdt:P279* wd:Q735156 . }
  UNION { ?sect wdt:P31/wdt:P279* wd:Q13414953 . }
  UNION { ?sect wdt:P361 wd:Q748 . }
  { ?item wdt:P19 ?place . }
  UNION { ?item wdt:P20 ?place . }
  UNION { ?item wdt:P937 ?place . }
  ?place wdt:P625 ?coord .
  OPTIONAL { ?item wdt:P569 ?birth . BIND(YEAR(?birth) AS ?birthYear) }
  OPTIONAL { ?item wdt:P570 ?death . BIND(YEAR(?death) AS ?deathYear) }
  OPTIONAL { ?item rdfs:label ?zhLabel FILTER(LANG(?zhLabel) = "zh") }
  OPTIONAL { ?item rdfs:label ?jaLabel FILTER(LANG(?jaLabel) = "ja") }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . ?item rdfs:label ?itemLabel . ?place rdfs:label ?placeLabel . }
} LIMIT 2000
"""

TRANSLATOR_QUERY = """
SELECT ?item ?itemLabel ?zhLabel ?jaLabel ?coord ?placeLabel ?birthYear ?deathYear WHERE {
  ?item wdt:P106 wd:Q4263842 .
  ?item wdt:P106 wd:Q333634 .
  { ?item wdt:P19 ?place . }
  UNION { ?item wdt:P20 ?place . }
  UNION { ?item wdt:P937 ?place . }
  ?place wdt:P625 ?coord .
  OPTIONAL { ?item wdt:P569 ?birth . BIND(YEAR(?birth) AS ?birthYear) }
  OPTIONAL { ?item wdt:P570 ?death . BIND(YEAR(?death) AS ?deathYear) }
  OPTIONAL { ?item rdfs:label ?zhLabel FILTER(LANG(?zhLabel) = "zh") }
  OPTIONAL { ?item rdfs:label ?jaLabel FILTER(LANG(?jaLabel) = "ja") }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . ?item rdfs:label ?itemLabel . ?place rdfs:label ?placeLabel . }
} LIMIT 2000
"""

QUERIES = {
    "work_location": build_place_query("P937"),
    "burial": build_place_query("P119"),
    "residence": build_place_query("P551"),
    "founder": FOUNDER_QUERY,
    "translator": TRANSLATOR_QUERY,
}

# Strong signals that reliably identify Buddhist figures. "monk" / "僧" /
# "saint" alone are too ambiguous (match Christian, Hindu, Shinto figures).
BUDDHIST_STRONG_KEYWORDS = [
    "buddhist", "buddhism", "佛教", "仏教", "佛學", "lama", "rinpoche",
    "dharma", "theravada", "mahayana", "vajrayana",
    "真言", "天台", "浄土", "真宗", "华严", "華嚴", "華厳",
    "dalai", "panchen", "bodhisattva", "nichiren", "zen ",
    "禅宗", "禪宗", "tiantai", "pure land", "日蓮", "曹洞", "臨済",
    "jodo", "jishu", "shingon", "tendai", "avalokit",
    "菩萨", "菩薩", "真言宗", "比丘", "bhiksu", "bhikkhu",
    "羅漢", "阿羅漢", "sangha", "pali canon", "藏传", "藏傳",
    "tibetan buddhist", "天台宗", "曹洞宗", "臨済宗",
    "禅師", "禪師", "chan master", "jōdo", "shinshū",
    "上人", "宗祖", "祖師", "祖师",
    "chan buddhism", "chinese buddhism", "japanese buddhist",
    "korean buddhist", "tibetan buddhism", "vietnamese buddhist",
    "佛學家", "佛学家", "法师", "法師", "高僧", "大師", "大师",
    "禅宗僧", "禪宗僧", "日本の僧", "中国の僧",  # explicit Japanese/Chinese monk
    "唐代僧", "宋代僧", "唐僧", "印度僧", "インドの仏教",
    "tulku", "活佛", "geshe", "khenpo",
]

# Block list — non-Buddhist religious identities. If these appear without a
# strong Buddhist signal, drop.
OTHER_RELIGION_KEYWORDS = [
    "hindu", "gospel", "brethren", "bishop", "abbot", "pastor",
    "christian saint", "christian ", "catholic", "protestant",
    "swami ", "基督", "富士信仰", "shinto", "神道", "fuji worship",
    "anglican", "lutheran", "presbyterian", "jesuit", "franciscan",
    "orthodox", "rabbi", "judaism", "islam", "muslim",
]

BUDDHIST_KEYWORDS = [
    "buddhist", "buddhism", "佛教", "僧", "和尚", "法师", "法師", "禅师", "禪師",
    "monk", "nun", "比丘", "比丘尼", "lama", "喇嘛", "rinpoche", "仁波切",
    "tulku", "活佛", "dharma", "dalai", "panchen", "班禅", "bodhisattva",
    "菩薩", "菩萨", "arhat", "阿罗汉", "羅漢", "高僧", "大师", "大師", "祖师", "祖師",
    "vajrayana", "theravada", "mahayana", "大乘", "小乘", "zen", "禪",
    "chan ", "禅", "tibetan buddhist", "藏传佛教", "藏傳佛教",
    "sangha", "sutra", "经师", "譯經", "译经", "pandita", "班智達", "班智达",
    "abbot", "abbess", "住持", "方丈", "法王",
    # Japanese
    "仏教", "僧侶", "禅僧", "尼僧", "浄土", "真宗", "天台", "真言",
    "日蓮", "曹洞", "臨済", "華厳", "律宗", "法相", "上人", "聖人",
    "阿闍梨", "阿闍黎", "宗祖", "開祖", "大僧正", "座主",
]

CHRISTIAN_KEYWORDS = [
    "christian", "catholic", "protestant", "jesuit", "franciscan",
    "dominican", "benedictine", "orthodox priest", "bishop", "archbishop",
    "cardinal", "pope ", "pastor", "reverend ", "基督教", "天主教", "新教",
    "东正教", "主教", "神父", "牧师", "牧師", "教宗", "教皇", "abbey",
    "hirsau", "cistercian", "augustinian", "carmelite",
]

# Clearly-secular occupations that override any Buddhist tagging — these
# descriptions indicate the person is primarily known as something non-religious.
SECULAR_KEYWORDS = [
    "actor", "actress", "演员", "演員", "singer", "歌手", "voice actor",
    "politician", "political figure", "political party", "政治家", "政治人物",
    "athlete", "运动员", "footballer", "足球", "basketball", "baseball",
    "tennis", "cricket", "rugby", "golf", "swimmer", "cyclist", "skater",
    "sportsperson", "sportswoman", "sportsman", "runner", "boxer",
    "businessperson", "entrepreneur", "businessman", "ceo", "investor",
    "musician", "音乐家", "音樂家", "guitarist", "band", "rapper", "pianist",
    "composer", "作曲家", "conductor", "指挥家", "violinist", "drummer",
    "filmmaker", "film director", "电影导演", "電影導演", "製片", "producer",
    "screenwriter", "cinematographer",
    "wrestler", "martial artist", "拳击",
    "fashion", "model", "模特", "designer", "设计师",
    "president of", "prime minister", "总统", "總統", "总理", "首相",
    "senator", "congressman", "mayor", "市长", "市長", "governor", "州长",
    "general ", "military officer", "admiral", "海军", "soldier",
    "queen of", "emperor of", "empress of", "king of", "prince of",
    "princess of", "duke of", "duchess of",
    "novelist", "poet", "小说家", "小說家", "诗人", "詩人", "writer", "作家",
    "author", "journalist", "记者", "記者", "playwright", "剧作家", "劇作家",
    "literary critic", "essayist", "literary scholar", "literary historian",
    "literary theorist", "literature professor", "music critic", "art critic",
    "film critic", "theatre critic",
    "economist", "philosopher", "哲学家", "哲學家",
    "academic", "professor", "教授", "lecturer", "scholar of",
    "physicist", "chemist", "biologist", "mathematician", "engineer",
    "scientist", "geologist", "astronomer", "physician", "医生", "醫生",
    "doctor of ", "surgeon", "psychiatrist", "psychologist", "anthropologist",
    "sociologist", "historian", "史学家", "史學家", "philologist", "linguist",
    "语言学", "語言學", "geographer",
    "painter", "画家", "畫家", "sculptor", "雕塑", "photographer", "摄影",
    "architect", "建筑师", "建築師", "illustrator", "cartoonist",
    "lawyer", "律师", "律師", "judge", "法官", "jurist", "legal scholar",
    "activist", "diplomat", "外交官", "ambassador", "大使", "revolutionary",
    "官员", "官員", "公务员", "civil servant", "bureaucrat",
    "editor of", "publisher", "broadcaster", "tv personality",
    "gymnast", "theatre director", "stage director", "theater director",
    "jewish", "judaism", "rabbi", "犹太",
    "muslim", "islamic", "imam", "伊斯兰", "伊斯蘭", "穆斯林",
    "hindu ", "hinduism", "印度教", "swami ",
    "samaritan", "arianism", "gnostic", "methodist", "presbyter", "quaker",
    "anglican", "lutheran", "baptist", "evangelical", "pentecostal",
    "saint of", "patron saint",
    "sexologist", "psychoanalyst",
]


# -----------------------------------------------------------------------------
# Fetchers
# -----------------------------------------------------------------------------
def query_sparql(sparql: str, retries: int = 3) -> list[dict]:
    params = urllib.parse.urlencode({"query": sparql, "format": "json"})
    url = f"{WIKIDATA_SPARQL_URL}?{params}"
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/sparql-results+json",
        })
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read())
            return data.get("results", {}).get("bindings", [])
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f"    429 rate limit, sleeping 30s (attempt {attempt+1})")
                time.sleep(30)
                continue
            raise
        except Exception as e:
            print(f"    Error: {e}, retry in 10s")
            time.sleep(10)
    return []


def parse_point(coord_str: str) -> tuple[float, float] | None:
    if not coord_str.startswith("Point("):
        return None
    inner = coord_str.removeprefix("Point(").removesuffix(")")
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


def batch_query_desc(qids: list[str]) -> dict[str, dict]:
    values = " ".join(f"wd:{q}" for q in qids)
    sparql = f"""
    SELECT ?item ?descEn ?descZh ?descJa WHERE {{
      VALUES ?item {{ {values} }}
      OPTIONAL {{ ?item schema:description ?descEn FILTER(LANG(?descEn) = "en") }}
      OPTIONAL {{ ?item schema:description ?descZh FILTER(LANG(?descZh) = "zh") }}
      OPTIONAL {{ ?item schema:description ?descJa FILTER(LANG(?descJa) = "ja") }}
    }}
    """
    bindings = query_sparql(sparql)
    result: dict[str, dict] = {}
    for b in bindings:
        item = b["item"]["value"].split("/")[-1]
        desc_en = b.get("descEn", {}).get("value", "")
        desc_zh = b.get("descZh", {}).get("value", "")
        desc_ja = b.get("descJa", {}).get("value", "")
        if item not in result:
            result[item] = {"en": desc_en, "zh": desc_zh, "ja": desc_ja}
        else:
            if desc_en and not result[item]["en"]:
                result[item]["en"] = desc_en
            if desc_zh and not result[item]["zh"]:
                result[item]["zh"] = desc_zh
            if desc_ja and not result[item].get("ja"):
                result[item]["ja"] = desc_ja
    return result


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main():
    # Load existing Q-IDs
    with open(EXISTING_PATH, encoding="utf-8") as f:
        existing = json.load(f)
    existing_qids = {r["wikidata_id"] for r in existing}
    print(f"Loaded {len(existing_qids)} existing Q-IDs")

    # Load existing descriptions
    existing_descs: dict[str, dict] = {}
    if DESC_PATH.exists():
        with open(DESC_PATH, encoding="utf-8") as f:
            existing_descs = json.load(f)
        print(f"Loaded {len(existing_descs)} existing descriptions")

    # Run each query, collect candidate records
    per_query_new: dict[str, int] = {}
    candidates: dict[str, dict] = {}  # qid -> record

    for name, sparql in QUERIES.items():
        print(f"\nQuerying: {name}...")
        t0 = time.time()
        bindings = query_sparql(sparql)
        print(f"  Got {len(bindings)} bindings ({time.time()-t0:.1f}s)")

        new_count = 0
        for b in bindings:
            wid = b.get("item", {}).get("value", "").split("/")[-1]
            if not wid:
                continue
            if wid in existing_qids:
                continue
            if wid in candidates:
                continue

            coord_val = b.get("coord", {}).get("value", "")
            parsed = parse_point(coord_val)
            if not parsed:
                continue
            lat, lng = parsed

            name_en = b.get("itemLabel", {}).get("value", "")
            name_zh = b.get("zhLabel", {}).get("value", "")
            name_ja = b.get("jaLabel", {}).get("value", "")
            place_name = b.get("placeLabel", {}).get("value", "")

            if name_en.startswith("Q") and name_en[1:].isdigit():
                name_en = ""
            if not name_zh and not name_en and not name_ja:
                continue

            birth_year = None
            death_year = None
            by = b.get("birthYear", {}).get("value", "")
            dy = b.get("deathYear", {}).get("value", "")
            try:
                if by:
                    birth_year = int(by)
            except ValueError:
                pass
            try:
                if dy:
                    death_year = int(dy)
            except ValueError:
                pass

            candidates[wid] = {
                "wikidata_id": wid,
                "name_zh": name_zh,
                "name_en": name_en,
                "name_ja": name_ja,
                "latitude": lat,
                "longitude": lng,
                "birth_year": birth_year,
                "death_year": death_year,
                "place_name": place_name,
                "source_query": name,
            }
            new_count += 1

        per_query_new[name] = new_count
        print(f"  New unique candidates: {new_count}")
        time.sleep(3)

    print(f"\nTotal unique new candidates (dedup vs existing): {len(candidates)}")

    # Fetch descriptions for those not in existing_descs
    missing_desc = [q for q in candidates if q not in existing_descs]
    print(f"\nFetching descriptions for {len(missing_desc)} new QIDs...")
    new_descs: dict[str, dict] = {}
    for i in range(0, len(missing_desc), 100):
        batch = missing_desc[i:i+100]
        try:
            result = batch_query_desc(batch)
            new_descs.update(result)
            if i % 500 == 0:
                print(f"  {i+len(batch)}/{len(missing_desc)}")
        except Exception as e:
            print(f"  ERROR {i}: {e}")
            time.sleep(10)
        time.sleep(2)

    # Combined description lookup
    all_descs = {**existing_descs, **new_descs}

    # Filter by description.
    # Rule: drop if description clearly shows non-Buddhist (Christian or
    # secular profession). Otherwise keep. Wikidata descriptions frequently
    # omit an explicit Buddhist signal for legitimately Buddhist figures
    # (e.g. "Japanese priest", "Tibetan scholar"), so we only drop on
    # POSITIVE evidence of non-Buddhist identity. Downstream curation can
    # further filter.
    kept: list[dict] = []
    dropped_christian = 0
    dropped_secular = 0
    for qid, rec in candidates.items():
        d = all_descs.get(qid, {})
        combined = f"{d.get('en', '')} {d.get('zh', '')} {d.get('ja', '')}".lower()
        rec["description_en"] = d.get("en", "")
        rec["description_zh"] = d.get("zh", "")
        rec["description_ja"] = d.get("ja", "")

        has_christian = any(k in combined for k in CHRISTIAN_KEYWORDS)
        has_buddhist = any(k in combined for k in BUDDHIST_KEYWORDS)
        has_secular = any(k in combined for k in SECULAR_KEYWORDS)

        has_buddhist_strong = any(k in combined for k in BUDDHIST_STRONG_KEYWORDS)
        has_other_religion = any(k in combined for k in OTHER_RELIGION_KEYWORDS)

        if has_christian and not has_buddhist_strong:
            dropped_christian += 1
            continue
        if has_secular and not has_buddhist_strong:
            dropped_secular += 1
            continue
        if has_other_religion and not has_buddhist_strong:
            dropped_christian += 1  # lump into christian/other-religion bucket
            continue
        # Strict: require a STRONG Buddhist signal. "monk" / "僧" alone are
        # too ambiguous (match Christian, Hindu, Shinto figures).
        if has_buddhist_strong:
            kept.append(rec)
        # else: drop (no description OR description lacks strong Buddhist signal)

    # Save output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(kept, f, ensure_ascii=False, indent=2)

    # Report
    print("\n" + "=" * 60)
    print("REPORT")
    print("=" * 60)
    print(f"Existing Q-IDs loaded:               {len(existing_qids)}")
    print("\nPer-query new unique candidates:")
    for name, n in per_query_new.items():
        print(f"  {name:20s}: {n}")
    print(f"\nTotal dedup candidates:              {len(candidates)}")
    print(f"Dropped (christian keywords):        {dropped_christian}")
    print(f"Dropped (secular keywords):          {dropped_secular}")
    print(f"Kept (final):                        {len(kept)}")
    print(f"\nOutput: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
