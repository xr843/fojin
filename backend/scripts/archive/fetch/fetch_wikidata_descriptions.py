"""Fetch Wikidata descriptions for all imported Buddhist persons.

Use descriptions (not occupations) to identify truly Buddhist figures:
- Keep: "Buddhist monk", "Chan master", "Tibetan lama", "Buddhist nun", etc.
- Delete: "American actor", "Thai politician", "Japanese singer", etc.

Run locally to avoid server IP blocking.
"""
import json
import time
import urllib.parse
import urllib.request

USER_AGENT = "FoJinBot/1.0"


def batch_query_desc(qids: list[str]) -> dict[str, dict]:
    """Fetch descriptions in en and zh for each QID."""
    values = " ".join(f"wd:{q}" for q in qids)
    sparql = f"""
    SELECT ?item ?descEn ?descZh WHERE {{
      VALUES ?item {{ {values} }}
      OPTIONAL {{ ?item schema:description ?descEn FILTER(LANG(?descEn) = "en") }}
      OPTIONAL {{ ?item schema:description ?descZh FILTER(LANG(?descZh) = "zh") }}
    }}
    """
    params = urllib.parse.urlencode({"query": sparql, "format": "json"})
    url = f"https://query.wikidata.org/sparql?{params}"
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/sparql-results+json",
    })
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read())
    result = {}
    for b in data.get("results", {}).get("bindings", []):
        item = b["item"]["value"].split("/")[-1]
        desc_en = b.get("descEn", {}).get("value", "")
        desc_zh = b.get("descZh", {}).get("value", "")
        if item not in result:
            result[item] = {"en": desc_en, "zh": desc_zh}
        else:
            if desc_en and not result[item]["en"]:
                result[item]["en"] = desc_en
            if desc_zh and not result[item]["zh"]:
                result[item]["zh"] = desc_zh
    return result


def main():
    with open("data/buddhist_persons.json", encoding="utf-8") as f:
        records = json.load(f)
    qids = [r["wikidata_id"] for r in records]
    print(f"Fetching descriptions for {len(qids)} QIDs...")

    descs = {}
    for i in range(0, len(qids), 100):
        batch = qids[i:i+100]
        try:
            result = batch_query_desc(batch)
            descs.update(result)
            if i % 500 == 0:
                print(f"  {i+len(batch)}/{len(qids)}")
        except Exception as e:
            print(f"  ERROR {i}: {e}")
            time.sleep(10)
        time.sleep(2)

    with open("data/person_descriptions.json", "w", encoding="utf-8") as f:
        json.dump(descs, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(descs)} descriptions")

    # Classify
    BUDDHIST_KEYWORDS = [
        "buddhist", "buddhism", "佛教", "僧", "和尚", "法师", "禅师", "禪師",
        "monk", "nun", "比丘", "比丘尼", "lama", "喇嘛", "rinpoche", "仁波切",
        "tulku", "活佛", "dharma", "dalai", "panchen", "班禅", "bodhisattva",
        "菩薩", "菩萨", "arhat", "阿罗汉", "羅漢", "高僧", "大师", "祖师",
        "vajrayana", "theravada", "mahayana", "大乘", "小乘", "zen ", "禪 ",
        "chan ", "禅 ", "tibetan buddhist", "藏传佛教",
    ]

    SECULAR_KEYWORDS = [
        "actor", "actress", "演员", "演員", "singer", "歌手",
        "politician", "政治家", "political", "politician",
        "athlete", "运动员", "footballer", "足球", "basketball",
        "businessperson", "entrepreneur", "businessman",
        "musician", "音乐家", "音樂家", "guitarist", "band",
        "filmmaker", "film director", "电影导演", "製片",
        "wrestler", "boxer", "martial artist", "拳击",
        "fashion", "model", "模特",
        "president of", "prime minister", "总统", "总理", "首相",
        "senator", "congressman", "mayor", "市长",
        "general ", "military officer", "admiral", "海军",
        "king of", "queen of", "emperor of", "empress of",  # secular royalty unless Buddhist
    ]

    keep = []
    delete = []
    ambiguous = []

    for rec in records:
        wid = rec["wikidata_id"]
        d = descs.get(wid, {})
        combined = f"{d.get('en', '')} {d.get('zh', '')}".lower()

        if not combined.strip():
            ambiguous.append(wid)
            continue

        has_buddhist = any(k in combined for k in BUDDHIST_KEYWORDS)
        has_secular = any(k in combined for k in SECULAR_KEYWORDS)

        if has_buddhist:
            keep.append(wid)  # Buddhist wins even if also secular
        elif has_secular:
            delete.append((wid, combined[:100]))
        else:
            ambiguous.append(wid)

    print(f"\nResults:")
    print(f"  Keep (Buddhist desc):   {len(keep)}")
    print(f"  Delete (secular desc):  {len(delete)}")
    print(f"  Ambiguous (no signal):  {len(ambiguous)}")

    # Save delete list
    with open("data/persons_delete_by_desc.json", "w", encoding="utf-8") as f:
        json.dump([w for w, _ in delete], f)

    # Sample
    print("\n=== Sample to DELETE ===")
    for wid, desc in delete[:20]:
        print(f"  {wid}: {desc}")


if __name__ == "__main__":
    main()
