"""Harvest Chinese Buddhist monks/nuns/masters (高僧大德) from Wikidata SPARQL.

TRACK A: structured harvest only. Produces raw + cleaned JSON files.
Does NOT write to the database.

Outputs:
  data/wikidata_persons_raw.json    - raw SPARQL bindings + metadata
  data/wikidata_persons_clean.json  - one record per person, FoJin-shaped

Strategy: 4 complementary SPARQL queries.
  Q1: occupation = Buddhist monk/nun/priest/teacher & Chinese citizenship
  Q2: religion = Buddhism & human & born in Chinese historical polities
  Q3: field of work = Buddhism & human & Chinese citizenship
  Q4: occupation subclass of Buddhist monk (Q4263842) - global, then filter
      to entries having a zh/zh-Hans label (broad 高僧传-style net)

Rate limit: 1s between queries.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
RAW_OUT = DATA_DIR / "wikidata_persons_raw.json"
CLEAN_OUT = DATA_DIR / "wikidata_persons_clean.json"

WIKIDATA_URL = "https://query.wikidata.org/sparql"
USER_AGENT = "FoJinBot/1.0 (https://fojin.app; Buddhist knowledge graph research)"

# Chinese historical polities (China + Taiwan + historical dynasties cluster)
# Q148 People's Republic of China, Q8646 Hong Kong, Q14773 Macau, Q865 Taiwan
# Also catch historical: wdt:P27/wdt:P279* wd:Q148 (transitive)

QUERIES: dict[str, str] = {
    "chinese_buddhist_clergy_occupation": """
SELECT ?item ?itemLabel ?itemDescription ?zhLabel ?zhHansLabel ?enLabel
       ?birth ?death ?birthPlace ?birthPlaceLabel ?coord
       ?image ?religionLabel ?sectLabel ?sect
WHERE {
  {
    ?item wdt:P106/wdt:P279* wd:Q4263842 .   # Buddhist monk
  } UNION {
    ?item wdt:P106 wd:Q1662844 .             # Buddhist priest
  } UNION {
    ?item wdt:P106 wd:Q193391 .              # Buddhist teacher
  } UNION {
    ?item wdt:P106 wd:Q161598 .              # nun (filtered later by zh label)
  } UNION {
    ?item wdt:P106 wd:Q327591 .
  }
  ?item wdt:P27/wdt:P279* wd:Q148 .          # Chinese citizen (transitive)
  OPTIONAL { ?item wdt:P569 ?birth . }
  OPTIONAL { ?item wdt:P570 ?death . }
  OPTIONAL {
    ?item wdt:P19 ?birthPlace .
    OPTIONAL { ?birthPlace wdt:P625 ?coord . }
  }
  OPTIONAL { ?item wdt:P18 ?image . }
  OPTIONAL { ?item wdt:P140 ?religion . }
  OPTIONAL { ?item wdt:P361 ?sect . }
  OPTIONAL { ?item rdfs:label ?zhLabel     FILTER(LANG(?zhLabel) = "zh") }
  OPTIONAL { ?item rdfs:label ?zhHansLabel FILTER(LANG(?zhHansLabel) = "zh-hans") }
  OPTIONAL { ?item rdfs:label ?enLabel     FILTER(LANG(?enLabel) = "en") }
  SERVICE wikibase:label {
    bd:serviceParam wikibase:language "en,zh" .
    ?item rdfs:label ?itemLabel .
    ?item schema:description ?itemDescription .
    ?birthPlace rdfs:label ?birthPlaceLabel .
    ?religion   rdfs:label ?religionLabel .
    ?sect       rdfs:label ?sectLabel .
  }
}
LIMIT 5000
""",
    "chinese_religion_buddhism_human": """
SELECT ?item ?itemLabel ?itemDescription ?zhLabel ?zhHansLabel ?enLabel
       ?birth ?death ?birthPlace ?birthPlaceLabel ?coord ?image ?sectLabel ?sect
WHERE {
  ?item wdt:P31 wd:Q5 .
  ?item wdt:P140 wd:Q748 .                    # religion: Buddhism
  ?item wdt:P27/wdt:P279* wd:Q148 .
  OPTIONAL { ?item wdt:P569 ?birth . }
  OPTIONAL { ?item wdt:P570 ?death . }
  OPTIONAL {
    ?item wdt:P19 ?birthPlace .
    OPTIONAL { ?birthPlace wdt:P625 ?coord . }
  }
  OPTIONAL { ?item wdt:P18 ?image . }
  OPTIONAL { ?item wdt:P361 ?sect . }
  OPTIONAL { ?item rdfs:label ?zhLabel     FILTER(LANG(?zhLabel) = "zh") }
  OPTIONAL { ?item rdfs:label ?zhHansLabel FILTER(LANG(?zhHansLabel) = "zh-hans") }
  OPTIONAL { ?item rdfs:label ?enLabel     FILTER(LANG(?enLabel) = "en") }
  SERVICE wikibase:label {
    bd:serviceParam wikibase:language "en,zh" .
    ?item rdfs:label ?itemLabel .
    ?item schema:description ?itemDescription .
    ?birthPlace rdfs:label ?birthPlaceLabel .
    ?sect       rdfs:label ?sectLabel .
  }
}
LIMIT 5000
""",
    "chinese_field_buddhism": """
SELECT ?item ?itemLabel ?itemDescription ?zhLabel ?zhHansLabel ?enLabel
       ?birth ?death ?birthPlace ?birthPlaceLabel ?coord ?image
WHERE {
  ?item wdt:P31 wd:Q5 .
  ?item wdt:P101 wd:Q9268 .                  # field of work: Buddhism
  ?item wdt:P27/wdt:P279* wd:Q148 .
  OPTIONAL { ?item wdt:P569 ?birth . }
  OPTIONAL { ?item wdt:P570 ?death . }
  OPTIONAL {
    ?item wdt:P19 ?birthPlace .
    OPTIONAL { ?birthPlace wdt:P625 ?coord . }
  }
  OPTIONAL { ?item wdt:P18 ?image . }
  OPTIONAL { ?item rdfs:label ?zhLabel     FILTER(LANG(?zhLabel) = "zh") }
  OPTIONAL { ?item rdfs:label ?zhHansLabel FILTER(LANG(?zhHansLabel) = "zh-hans") }
  OPTIONAL { ?item rdfs:label ?enLabel     FILTER(LANG(?enLabel) = "en") }
  SERVICE wikibase:label {
    bd:serviceParam wikibase:language "en,zh" .
    ?item rdfs:label ?itemLabel .
    ?item schema:description ?itemDescription .
    ?birthPlace rdfs:label ?birthPlaceLabel .
  }
}
LIMIT 5000
""",
    "global_buddhist_monk_with_zh_label": """
SELECT ?item ?itemLabel ?itemDescription ?zhLabel ?zhHansLabel ?enLabel
       ?birth ?death ?birthPlace ?birthPlaceLabel ?coord ?image
WHERE {
  ?item wdt:P106/wdt:P279* wd:Q4263842 .
  ?item rdfs:label ?zhLabel FILTER(LANG(?zhLabel) = "zh") .
  OPTIONAL { ?item wdt:P569 ?birth . }
  OPTIONAL { ?item wdt:P570 ?death . }
  OPTIONAL {
    ?item wdt:P19 ?birthPlace .
    OPTIONAL { ?birthPlace wdt:P625 ?coord . }
  }
  OPTIONAL { ?item wdt:P18 ?image . }
  OPTIONAL { ?item rdfs:label ?zhHansLabel FILTER(LANG(?zhHansLabel) = "zh-hans") }
  OPTIONAL { ?item rdfs:label ?enLabel     FILTER(LANG(?enLabel) = "en") }
  SERVICE wikibase:label {
    bd:serviceParam wikibase:language "en,zh" .
    ?item rdfs:label ?itemLabel .
    ?item schema:description ?itemDescription .
    ?birthPlace rdfs:label ?birthPlaceLabel .
  }
}
LIMIT 5000
""",
}

# Follow-up per-QID queries: teachers (P1066), students (P802), zh wiki sitelink.
# We batch these with VALUES clause.
LINKS_QUERY = """
SELECT ?item ?teacher ?teacherLabel ?student ?studentLabel ?zhwiki WHERE {
  VALUES ?item { %s }
  OPTIONAL { ?item wdt:P1066 ?teacher . }
  OPTIONAL { ?item wdt:P802  ?student . }
  OPTIONAL {
    ?zhwiki schema:about ?item ;
            schema:isPartOf <https://zh.wikipedia.org/> .
  }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "zh,en" . }
}
"""


def sparql(query: str, timeout: int = 180) -> list[dict]:
    params = urllib.parse.urlencode({"query": query, "format": "json"})
    url = f"{WIKIDATA_URL}?{params}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/sparql-results+json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    return data.get("results", {}).get("bindings", [])


def parse_point(coord: str) -> tuple[float, float] | None:
    if not coord or not coord.startswith("Point("):
        return None
    inner = coord.removeprefix("Point(").removesuffix(")")
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


def parse_year(iso: str) -> int | None:
    if not iso:
        return None
    # Wikidata dates: "+0602-01-01T00:00:00Z" or "-0123-01-01T00:00:00Z"
    s = iso
    sign = 1
    if s.startswith("-"):
        sign = -1
        s = s[1:]
    elif s.startswith("+"):
        s = s[1:]
    try:
        year_str = s.split("-")[0]
        return sign * int(year_str)
    except (ValueError, IndexError):
        return None


def cell(binding: dict, key: str) -> str:
    return binding.get(key, {}).get("value", "")


def qid_from_uri(uri: str) -> str:
    return uri.split("/")[-1] if uri else ""


def harvest() -> dict:
    raw = {
        "metadata": {
            "harvested_at": datetime.now(timezone.utc).isoformat(),
            "endpoint": WIKIDATA_URL,
            "queries": list(QUERIES.keys()),
        },
        "queries": {},
    }
    for name, q in QUERIES.items():
        print(f"\n[query] {name}", file=sys.stderr)
        t0 = time.time()
        try:
            bindings = sparql(q)
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            bindings = []
        print(f"  {len(bindings)} rows in {time.time() - t0:.1f}s", file=sys.stderr)
        raw["queries"][name] = bindings
        time.sleep(1.0)
    return raw


def enrich_links(qids: list[str]) -> dict[str, dict]:
    """Fetch teacher/student/zhwiki for harvested QIDs in batches of 100."""
    out: dict[str, dict] = {}
    batch_size = 100
    for i in range(0, len(qids), batch_size):
        batch = qids[i : i + batch_size]
        values = " ".join(f"wd:{q}" for q in batch)
        print(
            f"[links] batch {i // batch_size + 1}/{(len(qids) + batch_size - 1) // batch_size}",
            file=sys.stderr,
        )
        try:
            bindings = sparql(LINKS_QUERY % values)
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            bindings = []
        for b in bindings:
            q = qid_from_uri(cell(b, "item"))
            rec = out.setdefault(q, {"teachers": {}, "students": {}, "zhwiki": ""})
            t = qid_from_uri(cell(b, "teacher"))
            if t:
                rec["teachers"][t] = cell(b, "teacherLabel") or t
            s = qid_from_uri(cell(b, "student"))
            if s:
                rec["students"][s] = cell(b, "studentLabel") or s
            zw = cell(b, "zhwiki")
            if zw:
                rec["zhwiki"] = zw
        time.sleep(1.0)
    return out


def clean(raw: dict) -> list[dict]:
    merged: dict[str, dict] = {}
    for source_name, bindings in raw["queries"].items():
        for b in bindings:
            qid = qid_from_uri(cell(b, "item"))
            if not qid:
                continue
            rec = merged.setdefault(
                qid,
                {
                    "qid": qid,
                    "name_zh": "",
                    "name_en": "",
                    "description": "",
                    "birth_year": None,
                    "death_year": None,
                    "birth_place": "",
                    "birth_place_lat": None,
                    "birth_place_lng": None,
                    "image_url": "",
                    "sect": "",
                    "sources": [],
                },
            )
            if source_name not in rec["sources"]:
                rec["sources"].append(source_name)

            zh = cell(b, "zhLabel") or cell(b, "zhHansLabel")
            en = cell(b, "enLabel") or cell(b, "itemLabel")
            desc = cell(b, "itemDescription")
            if zh and not rec["name_zh"]:
                rec["name_zh"] = zh
            if en and not (en.startswith("Q") and en[1:].isdigit()) and not rec["name_en"]:
                rec["name_en"] = en
            if desc and not rec["description"]:
                rec["description"] = desc

            by = parse_year(cell(b, "birth"))
            dy = parse_year(cell(b, "death"))
            if by is not None and rec["birth_year"] is None:
                rec["birth_year"] = by
            if dy is not None and rec["death_year"] is None:
                rec["death_year"] = dy

            bp = cell(b, "birthPlaceLabel")
            if bp and not rec["birth_place"]:
                rec["birth_place"] = bp
            coord = parse_point(cell(b, "coord"))
            if coord and rec["birth_place_lat"] is None:
                rec["birth_place_lat"], rec["birth_place_lng"] = coord

            img = cell(b, "image")
            if img and not rec["image_url"]:
                rec["image_url"] = img

            sect = cell(b, "sectLabel")
            if sect and not rec["sect"]:
                rec["sect"] = sect

    # drop entries without any usable name (need zh OR en)
    cleaned = [r for r in merged.values() if r["name_zh"] or r["name_en"]]
    return cleaned


def to_fojin_schema(rec: dict, links: dict) -> dict:
    """Shape a cleaned record to match KGEntity (person) structure."""
    lk = links.get(rec["qid"], {})
    properties = {
        "birth_year": rec["birth_year"],
        "death_year": rec["death_year"],
        "birth_place": rec["birth_place"] or None,
        "birth_place_lat": rec["birth_place_lat"],
        "birth_place_lng": rec["birth_place_lng"],
        "sect": rec["sect"] or None,
        "image_url": rec["image_url"] or None,
        "teachers": lk.get("teachers") or {},
        "students": lk.get("students") or {},
        "source_queries": rec["sources"],
    }
    external_ids = {"wikidata": rec["qid"]}
    if lk.get("zhwiki"):
        external_ids["zh_wikipedia"] = lk["zhwiki"]
    return {
        "entity_type": "person",
        "name_zh": rec["name_zh"] or None,
        "name_en": rec["name_en"] or None,
        "description": rec["description"] or None,
        "properties": properties,
        "external_ids": external_ids,
    }


def report(cleaned: list[dict], links: dict[str, dict]) -> None:
    n = len(cleaned)
    with_zh = sum(1 for r in cleaned if r["name_zh"])
    with_year = sum(1 for r in cleaned if r["birth_year"] or r["death_year"])
    with_coord = sum(1 for r in cleaned if r["birth_place_lat"] is not None)
    with_image = sum(1 for r in cleaned if r["image_url"])
    with_sect = sum(1 for r in cleaned if r["sect"])
    with_teacher = sum(1 for r in cleaned if links.get(r["qid"], {}).get("teachers"))
    with_student = sum(1 for r in cleaned if links.get(r["qid"], {}).get("students"))
    with_zhwiki = sum(1 for r in cleaned if links.get(r["qid"], {}).get("zhwiki"))

    # century distribution
    buckets: dict[str, int] = {}
    for r in cleaned:
        y = r["birth_year"] or r["death_year"]
        if y is None:
            continue
        century = (y // 100) + (1 if y > 0 else 0)
        key = f"{century:+d}"
        buckets[key] = buckets.get(key, 0) + 1

    print("\n=== HARVEST REPORT ===", file=sys.stderr)
    print(f"Total unique persons: {n}", file=sys.stderr)
    print(f"  with name_zh     : {with_zh} ({100*with_zh/n:.0f}%)" if n else "", file=sys.stderr)
    print(
        f"  with birth/death : {with_year} ({100*with_year/n:.0f}%)" if n else "",
        file=sys.stderr,
    )
    print(
        f"  with coords      : {with_coord} ({100*with_coord/n:.0f}%)" if n else "",
        file=sys.stderr,
    )
    print(
        f"  with image       : {with_image} ({100*with_image/n:.0f}%)" if n else "",
        file=sys.stderr,
    )
    print(
        f"  with sect        : {with_sect} ({100*with_sect/n:.0f}%)" if n else "",
        file=sys.stderr,
    )
    print(
        f"  with teacher     : {with_teacher} ({100*with_teacher/n:.0f}%)" if n else "",
        file=sys.stderr,
    )
    print(
        f"  with student     : {with_student} ({100*with_student/n:.0f}%)" if n else "",
        file=sys.stderr,
    )
    print(
        f"  with zh wiki     : {with_zhwiki} ({100*with_zhwiki/n:.0f}%)" if n else "",
        file=sys.stderr,
    )
    print("\nCentury distribution (by birth or death year):", file=sys.stderr)
    for k in sorted(buckets.keys(), key=lambda x: int(x)):
        print(f"  {k:>4}c : {buckets[k]}", file=sys.stderr)
    print("\nNote: DB overlap check skipped (script does not touch DB by design).", file=sys.stderr)
    print(
        "      Run dedup by matching external_ids.wikidata and/or name_zh "
        "against kg_entities WHERE entity_type='person'.",
        file=sys.stderr,
    )


def main() -> None:
    raw = harvest()
    RAW_OUT.write_text(json.dumps(raw, ensure_ascii=False, indent=2))
    print(f"\n[write] {RAW_OUT}", file=sys.stderr)

    cleaned = clean(raw)
    qids = [r["qid"] for r in cleaned]
    print(f"[clean] {len(cleaned)} unique persons", file=sys.stderr)

    links = enrich_links(qids) if qids else {}

    shaped = [to_fojin_schema(r, links) for r in cleaned]
    CLEAN_OUT.write_text(
        json.dumps(
            {
                "metadata": {
                    "harvested_at": raw["metadata"]["harvested_at"],
                    "count": len(shaped),
                    "schema": "FoJin KGEntity(person)",
                },
                "persons": shaped,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"[write] {CLEAN_OUT}", file=sys.stderr)

    report(cleaned, links)


if __name__ == "__main__":
    main()
