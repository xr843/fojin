#!/usr/bin/env python3
"""
Fetch Treasury of Lives biographies via Wikidata SPARQL.

Why Wikidata (not direct scraping):
- treasuryoflives.org is behind Cloudflare Managed Challenge (returns 403 to
  non-browser clients), even for its robots.txt-allowed `FoJinBot` UA.
- Wikidata has Property P4138 "Treasury of Lives ID" on ~12,400 Tibetan
  Buddhist figures, with cross-linked Wikidata structured data:
  names (en/bo/zh), birth/death years, tradition, birth place coordinates,
  teachers, students, BDRC Person ID (P2477).
- Every returned record keeps its canonical tol_url for traceability.

Outputs: /home/lqsxi/projects/fojin/backend/data/treasury_of_lives.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DATA_DIR = Path("/home/lqsxi/projects/fojin/backend/data")
OUT_PATH = DATA_DIR / "treasury_of_lives.json"
BDRC_PLACES_PATH = DATA_DIR / "bdrc_places.json"

WDQS = "https://query.wikidata.org/sparql"
UA = "FoJinBot/1.0 (https://fojin.app; Buddhist studies) python-urllib"

# Fetch Treasury of Lives persons. One row per person; multi-valued fields
# (teachers, students, traditions, Tibetan labels) collapsed with GROUP_CONCAT.
SPARQL_CORE = r"""
SELECT ?person ?tolId ?enLabel ?zhLabel ?boLabel ?birth ?death ?bdrcPersonId
WHERE {
  ?person wdt:P4138 ?tolId.
  OPTIONAL { ?person rdfs:label ?enLabel. FILTER(LANG(?enLabel)="en") }
  OPTIONAL { ?person rdfs:label ?zhLabel. FILTER(LANG(?zhLabel)="zh") }
  OPTIONAL { ?person rdfs:label ?boLabel. FILTER(LANG(?boLabel)="bo") }
  OPTIONAL { ?person wdt:P569 ?birth. }
  OPTIONAL { ?person wdt:P570 ?death. }
  OPTIONAL { ?person wdt:P2477 ?bdrcPersonId. }
}
"""

SPARQL_TRADITION = r"""
SELECT ?person ?traditionLabel WHERE {
  ?person wdt:P4138 ?tolId;
          (wdt:P140|wdt:P1336|wdt:P135|wdt:P611) ?tradition.
  ?tradition rdfs:label ?traditionLabel. FILTER(LANG(?traditionLabel)="en")
}
"""

SPARQL_PLACES = r"""
SELECT ?person ?kind ?placeLabel ?placeWylie ?coord ?bdrcId WHERE {
  { ?person wdt:P4138 ?tolId; wdt:P19 ?place. BIND("birth" AS ?kind) }
  UNION
  { ?person wdt:P4138 ?tolId; (wdt:P551|wdt:P937) ?place. BIND("monastery" AS ?kind) }
  OPTIONAL { ?place rdfs:label ?placeLabel. FILTER(LANG(?placeLabel)="en") }
  OPTIONAL { ?place rdfs:label ?placeWylie. FILTER(LANG(?placeWylie)="bo") }
  OPTIONAL { ?place wdt:P625 ?coord. }
  OPTIONAL { ?place wdt:P2477 ?bdrcId. }
}
"""

SPARQL_TEACHERS = r"""
SELECT ?person ?otherLabel WHERE {
  ?person wdt:P4138 ?tolId; wdt:P1066 ?other.
  ?other rdfs:label ?otherLabel. FILTER(LANG(?otherLabel)="en")
}
"""

SPARQL_STUDENTS = r"""
SELECT ?person ?otherLabel WHERE {
  ?person wdt:P4138 ?tolId; wdt:P802 ?other.
  ?other rdfs:label ?otherLabel. FILTER(LANG(?otherLabel)="en")
}
"""

SPARQL_ALT_BO = r"""
SELECT ?person ?boAlt WHERE {
  ?person wdt:P4138 ?tolId; skos:altLabel ?boAlt. FILTER(LANG(?boAlt)="bo")
}
"""


def sparql_query(query: str) -> list[dict]:
    data = urlencode({"query": query, "format": "json"}).encode()
    req = Request(WDQS, data=data, headers={
        "User-Agent": UA,
        "Accept": "application/sparql-results+json",
        "Content-Type": "application/x-www-form-urlencoded",
    })
    with urlopen(req, timeout=300) as r:
        payload = json.loads(r.read().decode())
    return payload["results"]["bindings"]


def v(row: dict, key: str) -> str | None:
    cell = row.get(key)
    if not cell:
        return None
    val = cell.get("value")
    return val if val else None


def parse_year(date_str: str | None) -> int | None:
    if not date_str:
        return None
    # Formats: "1357-01-01T00:00:00Z" or negative years like "-0500-..."
    try:
        if date_str.startswith("-"):
            y = -int(date_str[1:].split("-")[0])
        else:
            y = int(date_str.split("-")[0])
        if -3000 <= y <= 2100:
            return y
    except (ValueError, IndexError):
        pass
    return None


def parse_point(wkt: str | None) -> tuple[float, float] | None:
    # "Point(91.49 29.765)"  -> (lat, lng)
    if not wkt or not wkt.startswith("Point("):
        return None
    try:
        inner = wkt[len("Point("):-1]
        lng_s, lat_s = inner.split()
        return float(lat_s), float(lng_s)
    except (ValueError, IndexError):
        return None


TRADITION_CANON = {
    "gelug": "Gelug", "dge lugs": "Gelug", "yellow hat": "Gelug",
    "kagyu": "Kagyu", "bka' brgyud": "Kagyu",
    "karma kagyu": "Kagyu", "drikung kagyu": "Kagyu", "drukpa": "Kagyu",
    "nyingma": "Nyingma", "rnying ma": "Nyingma",
    "sakya": "Sakya", "sa skya": "Sakya",
    "jonang": "Jonang", "bon": "Bon", "bön": "Bon",
    "rime": "Rime",
}


def canon_tradition(traditions_concat: str | None) -> str | None:
    if not traditions_concat:
        return None
    seen = []
    for t in traditions_concat.split("|"):
        tl = t.lower().strip()
        for key, canon in TRADITION_CANON.items():
            if key in tl and canon not in seen:
                seen.append(canon)
                break
    return "/".join(seen) if seen else traditions_concat.split("|")[0]


def load_bdrc_places() -> list[dict]:
    with open(BDRC_PLACES_PATH) as f:
        return json.load(f)


def build_bdrc_index(places: list[dict]) -> dict[str, dict]:
    """Index BDRC places by normalized Wylie and English names."""
    idx: dict[str, dict] = {}
    for p in places:
        keys = set()
        for field in ("name_bo", "name_en"):
            v = p.get(field)
            if v:
                keys.add(_norm(v))
        for alt in (p.get("alt_labels_bo") or []):
            keys.add(_norm(alt))
        for k in keys:
            if k and k not in idx:
                idx[k] = p
    return idx


def _norm(s: str) -> str:
    # Lowercase, drop apostrophes (wylie 'a-chung), strip trailing / and *,
    # collapse whitespace, keep alphanumerics + spaces.
    s = s.lower().replace("'", "").replace("*", "").replace("/", " ")
    out = "".join(ch if ch.isalnum() else " " for ch in s)
    return " ".join(out.split())


# Generic suffixes that obscure matches
_SUFFIXES = (" monastery", " dgon", " gon", " gompa", " gonpa", " gling")


def link_bdrc_place(name: str | None, bdrc_idx: dict[str, dict]) -> dict | None:
    if not name:
        return None
    key = _norm(name)
    if not key:
        return None
    if key in bdrc_idx:
        return bdrc_idx[key]
    # Try stripping common suffixes
    for suf in _SUFFIXES:
        if key.endswith(suf):
            trimmed = key[: -len(suf)].strip()
            if trimmed and trimmed in bdrc_idx:
                return bdrc_idx[trimmed]
    # Try adding " dgon" (common BDRC suffix)
    if (key + " dgon") in bdrc_idx:
        return bdrc_idx[key + " dgon"]
    return None


def run(label: str, query: str) -> list[dict]:
    for attempt in range(3):
        try:
            t0 = time.time()
            rows = sparql_query(query)
            print(f"[tol] {label}: {len(rows)} rows in {time.time()-t0:.1f}s", flush=True)
            time.sleep(2)
            return rows
        except Exception as e:
            wait = 5 * (attempt + 1)
            print(f"[tol] {label} attempt {attempt+1} failed: {e}; retry in {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"Failed after 3 attempts: {label}")


def main() -> int:
    bdrc_places = load_bdrc_places()
    bdrc_idx = build_bdrc_index(bdrc_places)
    bdrc_by_id = {p["bdrc_id"]: p for p in bdrc_places if p.get("bdrc_id")}
    print(f"[tol] Indexed {len(bdrc_idx)} BDRC place keys, {len(bdrc_by_id)} IDs", flush=True)

    core_rows = run("core", SPARQL_CORE)
    place_rows = run("places", SPARQL_PLACES)
    teacher_rows = run("teachers", SPARQL_TEACHERS)
    student_rows = run("students", SPARQL_STUDENTS)
    trad_rows = run("tradition", SPARQL_TRADITION)
    alt_rows = run("bo altLabels", SPARQL_ALT_BO)

    # Build base records from core
    by_qid: dict[str, dict] = {}
    for row in core_rows:
        qid = (v(row, "person") or "").rsplit("/", 1)[-1]
        tol_id = v(row, "tolId") or ""
        if not tol_id or qid in by_qid:
            continue
        by_qid[qid] = {
            "tol_url": f"https://treasuryoflives.org/biographies/view/{tol_id}",
            "tol_id": tol_id,
            "wikidata_qid": qid,
            "name_en": v(row, "enLabel"),
            "name_bo": v(row, "boLabel"),
            "name_bo_alt": [],
            "name_zh": v(row, "zhLabel"),
            "birth_year": parse_year(v(row, "birth")),
            "death_year": parse_year(v(row, "death")),
            "tradition": None,
            "birth_place": None,
            "main_monastery": None,
            "bdrc_person_id": v(row, "bdrcPersonId"),
            "bdrc_place_id": None,
            "latitude": None,
            "longitude": None,
            "coord_source": None,
            "teachers": [],
            "students": [],
        }

    # Attach Tibetan-script aliases
    for row in alt_rows:
        qid = (v(row, "person") or "").rsplit("/", 1)[-1]
        alt = v(row, "boAlt")
        rec = by_qid.get(qid)
        if rec and alt and alt != rec["name_bo"] and alt not in rec["name_bo_alt"]:
            rec["name_bo_alt"].append(alt)

    # Traditions (collect + canonicalize)
    trads: dict[str, list[str]] = {}
    for row in trad_rows:
        qid = (v(row, "person") or "").rsplit("/", 1)[-1]
        tl = v(row, "traditionLabel")
        if tl:
            trads.setdefault(qid, []).append(tl)
    for qid, tl in trads.items():
        if qid in by_qid:
            by_qid[qid]["tradition"] = canon_tradition("|".join(tl))

    # Teachers / students
    for row in teacher_rows:
        qid = (v(row, "person") or "").rsplit("/", 1)[-1]
        other = v(row, "otherLabel")
        rec = by_qid.get(qid)
        if rec and other and other not in rec["teachers"]:
            rec["teachers"].append(other)
    for row in student_rows:
        qid = (v(row, "person") or "").rsplit("/", 1)[-1]
        other = v(row, "otherLabel")
        rec = by_qid.get(qid)
        if rec and other and other not in rec["students"]:
            rec["students"].append(other)

    # Places: populate birth_place/main_monastery names, resolve coords.
    # Sort monastery rows first so they take priority in coord assignment.
    place_rows_sorted = sorted(
        place_rows, key=lambda r: 0 if v(r, "kind") == "monastery" else 1
    )
    for row in place_rows_sorted:
        qid = (v(row, "person") or "").rsplit("/", 1)[-1]
        rec = by_qid.get(qid)
        if rec is None:
            continue
        kind = v(row, "kind")
        name_en = v(row, "placeLabel")
        name_wy = v(row, "placeWylie")
        coord = parse_point(v(row, "coord"))
        pbdrc = v(row, "bdrcId")

        # Record the place name on the person
        if kind == "monastery" and name_en and not rec["main_monastery"]:
            rec["main_monastery"] = name_en
        if kind == "birth" and name_en and not rec["birth_place"]:
            rec["birth_place"] = name_en

        # If already have coords, skip resolution
        if rec["latitude"] is not None:
            continue

        # (1) BDRC ID direct
        if pbdrc and pbdrc in bdrc_by_id:
            bp = bdrc_by_id[pbdrc]
            if bp.get("lat") is not None:
                rec["latitude"] = bp["lat"]
                rec["longitude"] = bp["lng"]
                rec["bdrc_place_id"] = pbdrc
                rec["coord_source"] = "bdrc:" + pbdrc
                continue
        # (2) BDRC fuzzy name
        hit = link_bdrc_place(name_wy, bdrc_idx) or link_bdrc_place(name_en, bdrc_idx)
        if hit and hit.get("lat") is not None:
            rec["latitude"] = hit["lat"]
            rec["longitude"] = hit["lng"]
            rec["bdrc_place_id"] = hit["bdrc_id"]
            rec["coord_source"] = "bdrc:" + hit["bdrc_id"]
            continue
        # (3) Wikidata P625
        if coord:
            rec["latitude"], rec["longitude"] = coord
            rec["coord_source"] = "wikidata:" + (name_en or name_wy or "")

    records = sorted(by_qid.values(), key=lambda r: (r["birth_year"] or 9999, r["tol_id"]))
    with_coords = sum(1 for r in records if r["latitude"] is not None)
    with_bdrc_person = sum(1 for r in records if r["bdrc_person_id"])
    with_bdrc_place = sum(1 for r in records if r["bdrc_place_id"])

    OUT_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2))
    print(f"[tol] Saved {len(records)} biographies -> {OUT_PATH}", flush=True)
    print(f"[tol] With coords: {with_coords}", flush=True)
    print(f"[tol]   - linked to BDRC place: {with_bdrc_place}", flush=True)
    print(f"[tol]   - wikidata coords only: {with_coords - with_bdrc_place}", flush=True)
    print(f"[tol] With BDRC person ID link: {with_bdrc_person}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
