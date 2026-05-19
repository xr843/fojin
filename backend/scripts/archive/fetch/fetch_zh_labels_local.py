"""Fetch Chinese labels + descriptions from Wikidata. Run locally."""
import json
import os
import time
import urllib.parse
import urllib.request

USER_AGENT = "FoJinBot/1.0 (https://fojin.app)"
INPUT = "data/geo_qids.json"
OUTPUT = "data/wikidata_zh_labels.json"


def batch_query(qids: list[str]) -> dict[str, dict]:
    values = " ".join(f"wd:{q}" for q in qids)
    sparql = f"""
    SELECT ?item ?labelZh ?labelEn ?descZh ?descEn WHERE {{
      VALUES ?item {{ {values} }}
      OPTIONAL {{ ?item rdfs:label ?labelZh FILTER(LANG(?labelZh) IN ("zh", "zh-hans", "zh-cn", "zh-hant", "zh-tw")) }}
      OPTIONAL {{ ?item rdfs:label ?labelEn FILTER(LANG(?labelEn) = "en") }}
      OPTIONAL {{ ?item schema:description ?descZh FILTER(LANG(?descZh) IN ("zh", "zh-hans", "zh-cn", "zh-hant", "zh-tw")) }}
      OPTIONAL {{ ?item schema:description ?descEn FILTER(LANG(?descEn) = "en") }}
    }}
    """
    params = urllib.parse.urlencode({"query": sparql, "format": "json"})
    url = f"https://query.wikidata.org/sparql?{params}"
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/sparql-results+json",
    })
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    result: dict[str, dict] = {}
    for b in data.get("results", {}).get("bindings", []):
        item = b["item"]["value"].split("/")[-1]
        if item not in result:
            result[item] = {}
        for key_sparql, key_py in [("labelZh", "label_zh"), ("labelEn", "label_en"),
                                    ("descZh", "desc_zh"), ("descEn", "desc_en")]:
            val = b.get(key_sparql, {}).get("value", "")
            if val and not result[item].get(key_py):
                result[item][key_py] = val
    return result


def main():
    with open(INPUT) as f:
        qids = json.load(f)
    print(f"Total Q-IDs: {len(qids)}")

    all_results = {}
    if os.path.exists(OUTPUT):
        with open(OUTPUT) as f:
            all_results = json.load(f)
        print(f"Resuming: {len(all_results)} already fetched")

    for i in range(0, len(qids), 50):
        batch = [q for q in qids[i:i+50] if q not in all_results]
        if not batch:
            continue
        try:
            result = batch_query(batch)
            all_results.update(result)
        except Exception as e:
            print(f"  ERROR at {i}: {e}")
            time.sleep(15)
            continue

        if i % 500 == 0:
            print(f"  {i}/{len(qids)} — {len(all_results)} total")
            with open(OUTPUT, "w", encoding="utf-8") as f:
                json.dump(all_results, f, ensure_ascii=False, indent=2)
        time.sleep(1.5)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    # Stats
    zh_labels = sum(1 for v in all_results.values() if v.get("label_zh"))
    zh_descs = sum(1 for v in all_results.values() if v.get("desc_zh"))
    en_descs = sum(1 for v in all_results.values() if v.get("desc_en"))
    print(f"\nTotal fetched: {len(all_results)}")
    print(f"Has zh label: {zh_labels}")
    print(f"Has zh description: {zh_descs}")
    print(f"Has en description: {en_descs}")


if __name__ == "__main__":
    main()
