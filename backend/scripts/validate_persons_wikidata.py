"""Validate person entities via Wikidata P106 (occupation).

Keep only persons whose occupation is Buddhist clergy (monk, nun, priest, teacher, lama).
Delete persons who are politicians/celebrities/etc. mis-tagged with religion=Buddhism.

Run this LOCALLY (not on server — needs Wikidata SPARQL access).
"""
import json
import time
import urllib.parse
import urllib.request

USER_AGENT = "FoJinBot/1.0 (https://fojin.app)"

# Buddhist clergy P106 (occupation) classes — entity is Buddhist clergy
BUDDHIST_OCCUPATIONS = {
    "Q4263842",   # Buddhist monk
    "Q1662844",   # Buddhist priest
    "Q193391",    # Buddhist teacher (incorrect — this is actually theologian)
    "Q161598",    # Buddhist nun
    "Q122162",    # theologian (some Buddhist scholars)
    "Q2018370",   # Buddhist philosopher
    "Q3336976",   # Lama / Tibetan Buddhist master
    "Q208974",    # tulku
    "Q12353098",  # Buddhist scholar
    "Q21160022",  # Tibetan Buddhist monk
    "Q170790",    # monk (generic but often Buddhist)
    "Q34679",     # priest (generic)
    "Q171087",    # nun (generic)
    "Q18814623",  # autobiographer (some Buddhist memoirs)
    # Core ones:
    "Q201788",    # historian (some Buddhist scholars, keep if religion=buddhism)
    "Q36180",     # writer
    "Q1622272",   # university teacher
    "Q482980",    # author
}

def batch_query_p106(qids: list[str]) -> dict[str, list[str]]:
    values = " ".join(f"wd:{q}" for q in qids)
    sparql = f"""
    SELECT ?item ?occupation WHERE {{
      VALUES ?item {{ {values} }}
      ?item wdt:P106 ?occupation .
    }}
    """
    params = urllib.parse.urlencode({"query": sparql, "format": "json"})
    url = f"https://query.wikidata.org/sparql?{params}"
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/sparql-results+json",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    result = {}
    for b in data.get("results", {}).get("bindings", []):
        item = b["item"]["value"].split("/")[-1]
        occ = b["occupation"]["value"].split("/")[-1]
        result.setdefault(item, []).append(occ)
    return result


def main():
    # Load persons data
    with open("data/buddhist_persons.json", encoding="utf-8") as f:
        records = json.load(f)
    print(f"Loaded {len(records)} Buddhist persons")

    qids = [r["wikidata_id"] for r in records]
    print(f"Fetching P106 (occupations) in batches of 100...")

    occupations: dict[str, list[str]] = {}
    for i in range(0, len(qids), 100):
        batch = qids[i:i+100]
        try:
            result = batch_query_p106(batch)
            occupations.update(result)
            print(f"  {i+len(batch)}/{len(qids)} — {len(result)} with occupations")
        except Exception as e:
            print(f"  ERROR at {i}: {e}")
            time.sleep(10)
        time.sleep(2)

    # Classify
    buddhist_keep = []
    not_buddhist = []
    no_occupation = []

    CORE_BUDDHIST = {"Q4263842", "Q1662844", "Q193391", "Q161598",
                     "Q2018370", "Q3336976", "Q208974", "Q12353098",
                     "Q21160022", "Q170790", "Q171087"}

    for rec in records:
        wid = rec["wikidata_id"]
        occs = occupations.get(wid, [])
        if not occs:
            no_occupation.append(wid)
            continue
        is_buddhist = any(o in CORE_BUDDHIST for o in occs)
        if is_buddhist:
            buddhist_keep.append(wid)
        else:
            not_buddhist.append({"wikidata_id": wid, "name_zh": rec.get("name_zh"),
                                  "name_en": rec.get("name_en"), "occupations": occs})

    print(f"\n=== Results ===")
    print(f"Keep (Buddhist clergy):   {len(buddhist_keep)}")
    print(f"Delete (other occupation): {len(not_buddhist)}")
    print(f"No occupation data:        {len(no_occupation)} (keeping by default)")

    # Save delete list
    with open("data/persons_to_delete.json", "w", encoding="utf-8") as f:
        json.dump([x["wikidata_id"] for x in not_buddhist], f)
    print(f"\nSaved delete list → data/persons_to_delete.json")

    # Save details for review
    with open("data/persons_not_buddhist.json", "w", encoding="utf-8") as f:
        json.dump(not_buddhist, f, ensure_ascii=False, indent=2)
    print(f"Saved details → data/persons_not_buddhist.json")

    # Sample
    print("\n=== Sample of persons to DELETE ===")
    for x in not_buddhist[:15]:
        print(f"  {x['name_zh']} | {x['name_en']} | {x['occupations']}")


if __name__ == "__main__":
    main()
