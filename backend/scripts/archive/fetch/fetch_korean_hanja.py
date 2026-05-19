"""Fetch Hanja (Chinese character) equivalents for Korean Buddhist temples.

Strategy:
1. For each hangul temple name, query Korean Wikipedia API
2. Extract Hanja from infobox / {{한자}} templates / article wikitext
3. Fallback: query Wikidata SPARQL with Korean label, get zh label

Runs locally.
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request

USER_AGENT = "FoJinBot/1.0 (https://fojin.app)"
INPUT = "data/korean_hangul_names.json"
OUTPUT = "data/korean_hanja_map.json"


def query_wikidata_zh(korean_name: str) -> str | None:
    """Search Wikidata by Korean label, return Chinese label if found."""
    sparql = f"""
    SELECT ?item ?zh WHERE {{
      ?item rdfs:label "{korean_name}"@ko .
      ?item wdt:P31/wdt:P279* wd:Q5393308 .
      ?item rdfs:label ?zh FILTER(LANG(?zh) IN ("zh", "zh-hans", "zh-hant", "zh-cn", "zh-tw"))
    }} LIMIT 1
    """
    params = urllib.parse.urlencode({"query": sparql, "format": "json"})
    url = f"https://query.wikidata.org/sparql?{params}"
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/sparql-results+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        bindings = data.get("results", {}).get("bindings", [])
        if bindings:
            return bindings[0]["zh"]["value"]
    except Exception:
        pass
    return None


def query_wikipedia_ko_hanja(korean_name: str) -> str | None:
    """Query Korean Wikipedia for Hanja via parse API."""
    params = urllib.parse.urlencode({
        "action": "parse",
        "page": korean_name,
        "prop": "wikitext",
        "format": "json",
        "redirects": "1",
    })
    url = f"https://ko.wikipedia.org/w/api.php?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        wikitext = data.get("parse", {}).get("wikitext", {}).get("*", "")
        if not wikitext:
            return None
        # Match Hanja patterns
        # {{한자|...|漢字}} or {{lang|ko-hani|漢字}}
        for pattern in [
            r"한자\s*=\s*([一-龥]+)",
            r"\{\{한자\|[^\}]*\|([一-龥]+)",
            r"\{\{llang\|ko-hani\|([一-龥]+)",
            r"한자명\s*=\s*([一-龥]+)",
            r"'''[^'\(]*\(([一-龥]{2,}?)",  # 韓文名('''漢字)
        ]:
            m = re.search(pattern, wikitext)
            if m:
                return m.group(1)
        return None
    except Exception:
        return None


def main():
    with open(INPUT) as f:
        names = json.load(f)  # List of unique Korean hangul names
    print(f"Loaded {len(names)} Korean temple names to resolve")

    results = {}
    if os.path.exists(OUTPUT):
        with open(OUTPUT) as f:
            results = json.load(f)
        print(f"Resuming: {len(results)} already resolved")

    for i, name in enumerate(names):
        if name in results:
            continue

        # Try Wikidata first (faster, structured)
        hanja = query_wikidata_zh(name)
        source = "wikidata" if hanja else None

        # Fallback to Korean Wikipedia
        if not hanja:
            hanja = query_wikipedia_ko_hanja(name)
            source = "wikipedia_ko" if hanja else None

        if hanja:
            results[name] = {"hanja": hanja, "source": source}
            if len(results) % 20 == 0:
                print(f"  {i+1}/{len(names)} — found {len(results)}: {name} → {hanja}")
        else:
            results[name] = {"hanja": None, "source": None}

        if i % 100 == 0:
            with open(OUTPUT, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

        time.sleep(1.2)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    found = sum(1 for v in results.values() if v.get("hanja"))
    print(f"\nTotal: {len(results)} processed, {found} with Hanja")


if __name__ == "__main__":
    main()
