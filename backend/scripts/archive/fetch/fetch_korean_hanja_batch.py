"""Batch fetch Hanja for Korean temple names via Wikidata SPARQL (100 names per query)."""
import json
import os
import time
import urllib.parse
import urllib.request

USER_AGENT = "FoJinBot/1.0 (https://fojin.app)"
INPUT = "data/korean_hangul_names.json"
OUTPUT = "data/korean_hanja_map.json"


def batch_query_wikidata(ko_names: list[str]) -> dict[str, str]:
    """Batch query: multiple Korean labels → Chinese labels."""
    values = " ".join(f'"{escape_sparql(n)}"@ko' for n in ko_names)
    sparql = f"""
    SELECT DISTINCT ?korean ?zh WHERE {{
      VALUES ?korean {{ {values} }}
      ?item rdfs:label ?korean .
      ?item wdt:P31/wdt:P279* wd:Q5393308 .
      ?item rdfs:label ?zh FILTER(LANG(?zh) IN ("zh", "zh-hans", "zh-hant", "zh-cn", "zh-tw"))
    }}
    """
    params = urllib.parse.urlencode({"query": sparql, "format": "json"})
    url = f"https://query.wikidata.org/sparql?{params}"
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/sparql-results+json",
    })
    results: dict[str, str] = {}
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        for b in data.get("results", {}).get("bindings", []):
            ko = b["korean"]["value"]
            zh = b["zh"]["value"]
            if ko not in results:
                results[ko] = zh
    except Exception as e:
        print(f"  ERROR: {e}")
    return results


def escape_sparql(s: str) -> str:
    return s.replace('"', '\\"').replace("\\", "\\\\")


def main():
    with open(INPUT) as f:
        names = json.load(f)
    print(f"Total Korean names: {len(names)}")

    existing = {}
    if os.path.exists(OUTPUT):
        with open(OUTPUT) as f:
            existing = json.load(f)
        print(f"Resuming: {len(existing)} already done")

    results = dict(existing)
    BATCH = 80

    for i in range(0, len(names), BATCH):
        batch = [n for n in names[i:i+BATCH] if n not in results]
        if not batch:
            continue

        try:
            zh_map = batch_query_wikidata(batch)
            for name in batch:
                if name in zh_map:
                    results[name] = {"hanja": zh_map[name], "source": "wikidata"}
                else:
                    results[name] = {"hanja": None, "source": None}
        except Exception as e:
            print(f"  batch {i} error: {e}")
            time.sleep(15)
            continue

        found = sum(1 for v in results.values() if v.get("hanja"))
        print(f"  {i+len(batch)}/{len(names)} — found {found} total")

        if i % (BATCH*5) == 0:
            with open(OUTPUT, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
        time.sleep(2)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    found = sum(1 for v in results.values() if v.get("hanja"))
    print(f"\nDone: {len(results)} processed, {found} with Hanja from Wikidata")


if __name__ == "__main__":
    main()
