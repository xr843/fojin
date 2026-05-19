#!/usr/bin/env python3
"""Phase 2: Insert already-fetched Wikidata Buddhist persons.
Saves data to JSON first, then uses COPY for reliable insertion."""

import json
import re
import subprocess
import time
import urllib.request
import urllib.parse

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "FoJinBot/1.0 (https://fojin.app; bot@fojin.app)", "Accept": "application/json"}

def sparql_query(query):
    url = SPARQL_ENDPOINT + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["results"]["bindings"]
        except Exception as e:
            wait = 15 * (attempt + 1)
            print(f"  Query error (attempt {attempt+1}): {e}, waiting {wait}s...")
            time.sleep(wait)
    return []

def extract_qid(uri):
    m = re.search(r"(Q\d+)$", uri)
    return m.group(1) if m else None

def extract_year(date_str):
    if not date_str:
        return None
    m = re.match(r"-?(\d+)", date_str)
    if m:
        year = m.group(1).lstrip("0") or "0"
        return f"-{year}" if date_str.startswith("-") else year
    return None

def get_val(b, key):
    return b.get(key, {}).get("value", "")

def db_exec(sql):
    cmd = ["ssh", "admin@100.67.232.7",
           "cd /home/admin/fojin && docker compose exec -T postgres psql -U fojin -d fojin -c " +
           repr(sql)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f"  DB ERROR: {result.stderr[:200]}")
    return result.stdout

def db_copy_json(json_lines):
    """Use COPY with tab-separated values piped via stdin."""
    # Build TSV: entity_type\tname_zh\tname_en\tdescription\tproperties\texternal_ids
    tsv_lines = []
    for line in json_lines:
        def esc(s):
            if s is None:
                return "\\N"
            return s.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "")

        tsv_lines.append("\t".join([
            "person",
            esc(line["name_zh"]),
            esc(line["name_en"]),
            esc(line["description"]),
            esc(json.dumps(line["properties"], ensure_ascii=False)),
            esc(json.dumps(line["external_ids"], ensure_ascii=False)),
        ]))

    tsv_data = "\n".join(tsv_lines) + "\n"

    copy_sql = "COPY kg_entities (entity_type, name_zh, name_en, description, properties, external_ids) FROM STDIN"
    cmd = ["ssh", "admin@100.67.232.7",
           f"cd /home/admin/fojin && docker compose exec -T postgres psql -U fojin -d fojin -c \"{copy_sql}\""]
    result = subprocess.run(cmd, input=tsv_data, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"  COPY ERROR: {result.stderr[:300]}")
        return False
    print(f"  COPY result: {result.stdout.strip()}")
    return True

def get_existing_qids():
    out = db_exec("SELECT external_ids->>'wikidata' FROM kg_entities WHERE external_ids->>'wikidata' IS NOT NULL;")
    qids = set()
    for line in out.strip().split("\n"):
        line = line.strip()
        if line.startswith("Q"):
            qids.add(line)
    return qids

OCCUPATIONS = ["Q121594", "Q4263842", "Q16271564", "Q20826540"]
COUNTRIES = [("Q148","China"),("Q865","Taiwan"),("Q17","Japan"),("Q884","South Korea"),("Q668","India")]

def build_queries():
    queries = []
    for occ in OCCUPATIONS:
        for cqid, clabel in COUNTRIES:
            queries.append((f"occ={occ} country={clabel}", f"""
SELECT DISTINCT ?person ?personLabel ?personDescription ?birthDate ?deathDate WHERE {{
  ?person wdt:P106 wd:{occ} . ?person wdt:P27 wd:{cqid} .
  OPTIONAL {{ ?person wdt:P569 ?birthDate }} OPTIONAL {{ ?person wdt:P570 ?deathDate }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "zh,en,ja,ko" }}
}}"""))
        queries.append((f"occ={occ} no-country", f"""
SELECT DISTINCT ?person ?personLabel ?personDescription ?birthDate ?deathDate WHERE {{
  ?person wdt:P106 wd:{occ} .
  OPTIONAL {{ ?person wdt:P569 ?birthDate }} OPTIONAL {{ ?person wdt:P570 ?deathDate }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "zh,en,ja,ko" }}
}}"""))
    queries.append(("religion=Buddhism+leader", """
SELECT DISTINCT ?person ?personLabel ?personDescription ?birthDate ?deathDate WHERE {
  ?person wdt:P140 wd:Q748 .
  { ?person wdt:P106 wd:Q432386 } UNION { ?person wdt:P106 wd:Q955464 } .
  OPTIONAL { ?person wdt:P569 ?birthDate } OPTIONAL { ?person wdt:P570 ?deathDate }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "zh,en,ja,ko" }
}"""))
    return queries

def main():
    print("=== Wikidata Buddhist Persons Import (Phase 2) ===")

    print("\n1. Getting existing QIDs from database...")
    existing = get_existing_qids()
    print(f"   Found {len(existing)} existing Wikidata persons")

    all_persons = {}

    for label, query in build_queries():
        print(f"\n2. Querying: {label}...")
        results = sparql_query(query)
        print(f"   Got {len(results)} results")

        for r in results:
            qid = extract_qid(get_val(r, "person"))
            if not qid or qid in existing:
                continue

            name = get_val(r, "personLabel")
            desc = get_val(r, "personDescription")

            if qid not in all_persons:
                all_persons[qid] = {"name_zh": None, "name_en": None, "description": None,
                                     "birth_year": None, "death_year": None, "country": ""}

            p = all_persons[qid]

            if name:
                if re.search(r"[\u4e00-\u9fff]", name) and not p["name_zh"]:
                    p["name_zh"] = name
                elif re.match(r"[A-Za-z]", name) and not p["name_en"]:
                    p["name_en"] = name

            if desc and not p["description"]:
                p["description"] = desc

            birth = extract_year(get_val(r, "birthDate"))
            if birth and not p["birth_year"]:
                p["birth_year"] = birth

            death = extract_year(get_val(r, "deathDate"))
            if death and not p["death_year"]:
                p["death_year"] = death

            if "country=" in label:
                c = label.split("country=")[1].split()[0]
                if c and not p["country"]:
                    p["country"] = c

        time.sleep(8)

    print(f"\n=== Total new persons from Wikidata: {len(all_persons)} ===")

    new_persons = {qid: p for qid, p in all_persons.items() if p["name_zh"] or p["name_en"]}
    print(f"With valid names: {len(new_persons)}")

    if not new_persons:
        print("Nothing to import!")
        return

    # Build records for COPY
    print("\n3. Inserting via COPY...")
    records = []
    for qid, p in new_persons.items():
        props = {"source": "wikidata"}
        for k in ["country", "birth_year", "death_year"]:
            if p.get(k):
                props[k] = p[k]

        records.append({
            "name_zh": p["name_zh"] or p["name_en"] or "unknown",
            "name_en": p["name_en"],
            "description": (p["description"] or "")[:500] or None,
            "properties": props,
            "external_ids": {"wikidata": qid},
        })

    # Insert in batches of 500
    total = 0
    for i in range(0, len(records), 500):
        batch = records[i:i+500]
        ok = db_copy_json(batch)
        if ok:
            total += len(batch)
            print(f"  Total inserted: {total}")
        else:
            # Fallback: try one by one
            print(f"  Batch failed, trying one by one...")
            for rec in batch:
                ok = db_copy_json([rec])
                if ok:
                    total += 1

    print(f"\n=== Done! Imported {total} new Buddhist persons ===")

    out = db_exec("SELECT count(*) FROM kg_entities WHERE entity_type='person';")
    for line in out.strip().split("\n"):
        line = line.strip()
        if line.isdigit():
            print(f"Total persons now: {line}")

if __name__ == "__main__":
    main()
