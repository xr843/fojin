"""
Fetch Tibetan Buddhist persons (lamas, tulkus, scholars) from BDRC
via their public Linked Data endpoint.

Data source: https://ldspdi.bdrc.io/ (BDRC LDS-PDI templated queries + resource JSON)
License: BDRC data is CC-BY 4.0 (per https://www.bdrc.io/copyright-and-license/)
Ontology: http://purl.bdrc.io/ontology/core/

Runs LOCALLY to avoid IP restrictions on the production server.
Output: backend/data/bdrc_persons.json

Strategy (seed-based graph crawl + place-linkage filter):
  1. Load the known BDRC places (G-IDs with coords) from bdrc_places.json.
  2. Discover candidate Person P-IDs via personGraph Lucene search on seed
     Wylie names of famous lineages, schools, and persons.
  3. For each candidate, fetch full Person JSON (ResInfo).
  4. Extract birth/death years, teachers, students, tradition, and all
     personEvent -> eventWhere links (which point to BDRC G-IDs).
  5. Keep only persons with at least one eventWhere in our known-coord G-ID set.
  6. Assign primary_place = eventWhere of PersonOccupiesSeat / main seat event
     (fallback: birth event's place, or first matched place).
  7. Inherit coordinates from the primary_place.
  8. BFS-expand via personStudentOf / personTeacherOf edges up to a cap.

Each record:
    {
      "bdrc_id": "P64",
      "name_zh": "宗喀巴",
      "name_bo": "tsong kha pa blo bzang grags pa/",
      "name_en": "Tsongkhapa Lobzang Drakpa",
      "birth_year": 1357,
      "death_year": 1419,
      "associated_places": ["G337", "G1956", "G2354"],
      "primary_place": "G337",
      "latitude": 29.7650,
      "longitude": 91.4900,
      "teachers": ["P8805", "P2010", "P1558"],
      "students": ["P58", "P4174", ...],
      "school": "Geluk",
      "wikidata": "Q323439",
      "source": "bdrc",
      "source_url": "https://library.bdrc.io/show/bdr:P64"
    }

Usage:
    python3 scripts/fetch_bdrc_persons.py
    python3 scripts/fetch_bdrc_persons.py --max 2000 --sleep 2.0
"""

import argparse
import json
import sys
import time
import urllib.parse
from collections import deque
from pathlib import Path

import httpx

BDRC_PERSON_GRAPH = "https://ldspdi.bdrc.io/lib/personGraph"
BDRC_RESOURCE = "https://ldspdi.bdrc.io/resource"

USER_AGENT = "FoJin/1.0 (buddhist digital humanities; +https://fojin.app)"

# Seed Wylie terms for discovering person P-IDs via personGraph Lucene search.
# Each seed returns up to ~1500 loosely-related persons; we'll filter by
# place-linkage downstream, so broad seeds are safe.
SEED_NAMES = [
    # Lineage / school names (discover school members)
    "dge lugs", "bka' brgyud", "sa skya", "rnying ma", "jo nang", "bon po",
    "karma bka' brgyud", "'bri gung bka' brgyud", "stag lung bka' brgyud",
    "'brug pa bka' brgyud", "shangs pa bka' brgyud",
    # Famous founders / figures
    "tsong kha pa", "padma 'byung gnas", "atisha", "mi la ras pa",
    "mar pa", "sgam po pa", "na ro pa", "ti lo pa", "sa skya paN Di ta",
    "'phags pa", "bsod nams rtse mo", "grags pa rgyal mtshan",
    "sa chen kun dga' snying po", "bu ston", "klong chen pa",
    "karma pa", "dalai bla ma", "paN chen bla ma", "ye shes mtsho rgyal",
    "vimalamitra", "gshen rab mi bo", "rgyal ba yang dgon pa",
    "zhang rin po che", "rwa lo tsA ba", "'gos lo tsA ba",
    # Tulku / incarnation lineages
    "dus gsum mkhyen pa", "karma pakshi", "rang byung rdo rje",
    "rol pa'i rdo rje", "de bzhin gshegs pa", "mi bskyod rdo rje",
    "dbang phyug rdo rje", "chos grags rgya mtsho",
    "dge 'dun grub", "dge 'dun rgya mtsho", "bsod nams rgya mtsho",
    "yon tan rgya mtsho", "blo bzang rgya mtsho", "tshangs dbyangs rgya mtsho",
    "bskal bzang rgya mtsho", "'jam dpal rgya mtsho", "lung rtogs rgya mtsho",
    "mkhas grub rgya mtsho", "'phrin las rgya mtsho", "thub bstan rgya mtsho",
    "bstan 'dzin rgya mtsho",
    # Panchen Lamas
    "blo bzang chos kyi rgyal mtshan", "blo bzang ye shes",
    "blo bzang dpal ldan ye shes", "bstan pa'i nyi ma",
    "bstan pa'i dbang phyug", "chos kyi grags pa", "chos kyi nyi ma",
    # Terton / treasure revealers
    "gter ston", "nyang ral", "g.yu thog", "ratna gling pa",
    "padma gling pa", "sangs rgyas gling pa", "rig 'dzin rgod ldem",
    # Scholars / translators
    "lo tsA ba", "mkhan po", "dge bshes", "sprul sku", "rin po che",
    "rgyal tshab", "mkhas grub", "'jam dbyangs", "tA ra nA tha",
    "dol po pa", "gser mdog paN chen",
    # Monastery-related titles
    "bla ma", "slob dpon", "mkhan chen", "abbot",
]

# Pre-seed P-IDs for famous persons (confirmed via BDRC library UI).
# These get crawled first so the BFS expansion starts from high-signal
# historical figures. Their teachers/students ripple out to fill the pool.
KNOWN_FAMOUS_PIDS = [
    "P64",    # Tsongkhapa (Geluk founder)
    "P155",   # Buton Rinchen Drup
    "P1614",  # Drakpa Gyaltsen (Sakya)
    "P1615",  # Sachen Kunga Nyingpo (Sakya)
    "P1649",  # Dalai Lama 14
    "P1856",  # Dalai Lama 1 (Gedun Drup)?
    "P2626",  # Serdog Panchen
    "P1",     # often the 1st Karmapa
    "P3",     # Karmapa lineage starters
    "P5",
    "P12",
    "P55",
    "P58",    # Gyaltsab Je
    "P80",    # Khedrup Je
    "P100",
    "P123",
    "P143",
    "P223",
    "P282",   # Milarepa
    "P285",   # Marpa
    "P314",   # Gampopa
    "P364",
    "P386",
    "P450",   # Atisha
    "P588",   # Dusum Khyenpa (1st Karmapa)
    "P826",   # Karma Pakshi (2nd Karmapa)
    "P1030",  # Rangjung Dorje (3rd Karmapa)
    "P1068",
    "P1124",  # Mikyo Dorje (8th Karmapa)
    "P1132",
    "P1428",  # Longchenpa
    "P1453",  # Jigme Lingpa
    "P1558",
    "P2010",
    "P2273",  # Sakya Pandita
    "P2732",  # Sakya Trizin lineage
    "P4956",  # Taranatha
    "P5392",
    "P6065",  # Mipham Rinpoche
    "P6387",
    "P7129",  # Shabkar
    "P7663",  # Longchenpa variant
    "P8204",  # Padmasambhava variant
    "P8205",  # Padmasambhava
    "P8805",
    "P8LS12",
    "G300",   # placeholder no - drop
]
# drop placeholder
KNOWN_FAMOUS_PIDS = [p for p in KNOWN_FAMOUS_PIDS if p.startswith("P")]


def pid_sort_key(pid):
    """Sort key that prioritizes short numeric P-IDs (older BDRC records).
    P64 < P155 < P1649 < P00EGS1016721 < P8LS76454.
    """
    # strip "P", check if purely numeric
    body = pid[1:]
    if body.isdigit():
        return (0, int(body), pid)
    # prefix-coded (e.g. P00EGS, P8LS, P1KG) come later
    return (1, len(pid), pid)


SCHOOL_MAP = {
    "TraditionGeluk": "Geluk",
    "TraditionKagyu": "Kagyu",
    "TraditionSakya": "Sakya",
    "TraditionNyingma": "Nyingma",
    "TraditionJonang": "Jonang",
    "TraditionBon": "Bon",
    "TraditionKarmaKagyu": "Karma Kagyu",
    "TraditionDrikungKagyu": "Drikung Kagyu",
    "TraditionTaklungKagyu": "Taklung Kagyu",
    "TraditionDrukpaKagyu": "Drukpa Kagyu",
    "TraditionShangpaKagyu": "Shangpa Kagyu",
    "TraditionDakpoKagyu": "Dakpo Kagyu",
    "TraditionBarawaKagyu": "Barawa Kagyu",
    "TraditionYazangKagyu": "Yazang Kagyu",
    "TraditionTshalpaKagyu": "Tshalpa Kagyu",
    "TraditionZhalu": "Zhalu",
    "TraditionKadam": "Kadam",
    "TraditionBuddhist": "Buddhist",
}

# event types that indicate "main seat" relationship
MAIN_SEAT_EVENTS = {
    "PersonOccupiesSeat",
    "PersonMainSeat",
    "PersonAssumesOffice",
}


def fetch_person_graph(client, name):
    """Lucene search on personGraph. Returns dict of URI->preds (list)."""
    try:
        r = client.get(
            BDRC_PERSON_GRAPH,
            params={"L_NAME": name, "LG_NAME": "bo-x-ewts"},
            timeout=60.0,
        )
        r.raise_for_status()
        return r.json().get("main", {})
    except Exception as e:
        print(f"  personGraph error for {name!r}: {e}", file=sys.stderr)
        return {}


def fetch_person_resource(client, pid):
    """Fetch full ResInfo JSON for a Person P-ID. Returns dict of URI->preds (dict)."""
    try:
        r = client.get(f"{BDRC_RESOURCE}/{pid}.json", timeout=60.0)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  resource error for {pid}: {e}", file=sys.stderr)
        return {}


def preds_to_dict(preds):
    """Normalise: convert list-form ([{type, value, xml:lang}]) to dict {pred: [vals]}."""
    if isinstance(preds, dict):
        return preds
    out = {}
    for item in preds:
        t = item.get("type")
        if not t:
            continue
        out.setdefault(t, []).append(
            {
                "value": item.get("value"),
                "xml:lang": item.get("xml:lang"),
                "datatype": item.get("datatype"),
            }
        )
    return out


def parse_person_record(pid, graph, place_lookup):
    """From a person's full resource JSON, extract one normalised record.
    Returns None if the person has no eventWhere in our place_lookup.
    """
    person_uri = f"http://purl.bdrc.io/resource/{pid}"
    person_preds = graph.get(person_uri)
    if not person_preds:
        return None
    person_preds = preds_to_dict(person_preds)

    # Confirm it's a Person
    types = [
        v["value"].rsplit("/", 1)[-1]
        for v in person_preds.get("http://www.w3.org/1999/02/22-rdf-syntax-ns#type", [])
    ]
    if "Person" not in types:
        return None

    # Names (prefLabel with multiple langs).
    # BDRC ResInfo JSON uses `lang`, personGraph uses `xml:lang`.
    def _lang(v):
        return v.get("lang") or v.get("xml:lang") or ""

    name_zh = name_bo = name_en = None
    for v in person_preds.get("http://www.w3.org/2004/02/skos/core#prefLabel", []):
        lang = _lang(v)
        val = v.get("value", "")
        if lang == "zh-Hans" and not name_zh:
            name_zh = val
        elif lang == "bo-x-ewts" and not name_bo:
            name_bo = val
        elif lang == "en" and not name_en:
            name_en = val
    # Fallback: look at personName nested nodes
    if not name_en or not name_zh:
        for nm_ref in person_preds.get("http://purl.bdrc.io/ontology/core/personName", []):
            nm_uri = nm_ref.get("value")
            nm_preds = preds_to_dict(graph.get(nm_uri, {}))
            for v in nm_preds.get("http://www.w3.org/2000/01/rdf-schema#label", []):
                lang = _lang(v)
                val = v.get("value", "")
                if lang == "en" and not name_en:
                    name_en = val
                elif lang == "zh-Hans" and not name_zh:
                    name_zh = val

    # Teachers / students
    teachers = [
        v["value"].rsplit("/", 1)[-1]
        for v in person_preds.get("http://purl.bdrc.io/ontology/core/personStudentOf", [])
    ]
    students = [
        v["value"].rsplit("/", 1)[-1]
        for v in person_preds.get("http://purl.bdrc.io/ontology/core/personTeacherOf", [])
    ]

    # Tradition / school
    school = None
    for v in person_preds.get("http://purl.bdrc.io/ontology/core/associatedTradition", []):
        key = v["value"].rsplit("/", 1)[-1]
        school = SCHOOL_MAP.get(key, key.replace("Tradition", ""))
        break

    # sameAs -> wikidata
    wikidata_id = None
    for v in person_preds.get("http://www.w3.org/2002/07/owl#sameAs", []):
        val = v.get("value", "")
        if "wikidata.org/entity/" in val:
            wikidata_id = val.rsplit("/", 1)[-1]
            break

    # Events -> birth/death year + place links
    birth_year = death_year = None
    associated_places = []
    primary_place = None
    # Priority order for primary_place:
    #   1. PersonOccupiesSeat / PersonAssumesOffice
    #   2. PersonMainSeat
    #   3. PersonBirth
    #   4. first matched place
    seat_place = None
    birth_place = None

    for ev_ref in person_preds.get("http://purl.bdrc.io/ontology/core/personEvent", []):
        ev_uri = ev_ref.get("value")
        ev_preds = preds_to_dict(graph.get(ev_uri, {}))
        ev_type = None
        for v in ev_preds.get("http://www.w3.org/1999/02/22-rdf-syntax-ns#type", []):
            ev_type = v["value"].rsplit("/", 1)[-1]
            break
        # Year
        year = None
        for key in (
            "http://purl.bdrc.io/ontology/core/onYear",
            "http://purl.bdrc.io/ontology/core/notBefore",
        ):
            for v in ev_preds.get(key, []):
                try:
                    year = int(str(v["value"])[:4])
                    break
                except (ValueError, TypeError):
                    pass
            if year:
                break
        if ev_type == "PersonBirth" and year:
            birth_year = year
        elif ev_type == "PersonDeath" and year:
            death_year = year
        # Place
        for v in ev_preds.get("http://purl.bdrc.io/ontology/core/eventWhere", []):
            gid = v["value"].rsplit("/", 1)[-1]
            if gid in place_lookup:
                if gid not in associated_places:
                    associated_places.append(gid)
                if ev_type in MAIN_SEAT_EVENTS and not seat_place:
                    seat_place = gid
                elif ev_type == "PersonBirth" and not birth_place:
                    birth_place = gid

    if not associated_places:
        return None

    primary_place = seat_place or birth_place or associated_places[0]
    place = place_lookup[primary_place]

    return {
        "bdrc_id": pid,
        "name_zh": name_zh,
        "name_bo": name_bo,
        "name_en": name_en,
        "birth_year": birth_year,
        "death_year": death_year,
        "associated_places": associated_places,
        "primary_place": primary_place,
        "latitude": place["lat"],
        "longitude": place["lng"],
        "teachers": teachers,
        "students": students,
        "school": school,
        "wikidata": wikidata_id,
        "source": "bdrc",
        "source_url": f"https://library.bdrc.io/show/bdr:{pid}",
    }


def discover_candidates(client, seeds, sleep_sec):
    """Lucene-search each seed on personGraph; collect unique P-IDs."""
    candidates = set()
    for i, s in enumerate(seeds, 1):
        main = fetch_person_graph(client, s)
        added = 0
        for uri in main:
            rid = uri.rsplit("/", 1)[-1]
            if rid.startswith("P") and not rid.startswith("PR"):
                if rid not in candidates:
                    candidates.add(rid)
                    added += 1
        print(
            f"  [seed {i:2d}/{len(seeds)}] {s!r:32s} +{added:4d} new (total={len(candidates)})",
            flush=True,
        )
        time.sleep(sleep_sec)
    return candidates


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--places",
        default=str(Path(__file__).resolve().parents[1] / "data" / "bdrc_places.json"),
    )
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[1] / "data" / "bdrc_persons.json"),
    )
    parser.add_argument("--max", type=int, default=2000, help="max persons to keep")
    parser.add_argument("--max-fetch", type=int, default=8000, help="max candidate P-IDs to fetch")
    parser.add_argument("--sleep", type=float, default=2.0, help="sleep between resource fetches")
    parser.add_argument("--seed-sleep", type=float, default=1.0, help="sleep between seed queries")
    args = parser.parse_args()

    # Load places
    place_lookup = {}
    with open(args.places, encoding="utf-8") as f:
        for p in json.load(f):
            place_lookup[p["bdrc_id"]] = p
    print(f"Loaded {len(place_lookup)} BDRC places with coords.")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        http2=False,
    ) as client:
        # Phase 1: discover candidate P-IDs via seed searches
        print(f"\n=== Phase 1: Discovering candidates via {len(SEED_NAMES)} seed searches ===")
        candidates = discover_candidates(client, SEED_NAMES, args.seed_sleep)
        print(f"\nTotal unique candidate P-IDs: {len(candidates)}")

        # Phase 2: fetch each candidate's full JSON, filter to those with
        # events in our place set. Include BFS expansion via teachers/students.
        # Merge in the known-famous seed list first so crawl starts from
        # high-signal historical figures.
        print(f"\n=== Phase 2: Fetching up to {args.max_fetch} candidates (sleep={args.sleep}s) ===")
        for pid in KNOWN_FAMOUS_PIDS:
            candidates.add(pid)
        # Prefer short-numeric P-IDs first (older = more famous); KNOWN_FAMOUS
        # come at front via pid_sort_key.
        ordered = sorted(candidates, key=pid_sort_key)
        queue = deque(ordered)
        visited = set()
        records = {}
        fetched = 0

        while queue and fetched < args.max_fetch and len(records) < args.max:
            pid = queue.popleft()
            if pid in visited:
                continue
            visited.add(pid)
            fetched += 1

            graph = fetch_person_resource(client, pid)
            if not graph:
                time.sleep(args.sleep)
                continue

            rec = parse_person_record(pid, graph, place_lookup)
            if rec:
                records[pid] = rec
                # BFS: enqueue teachers/students for expansion
                for rid in rec["teachers"] + rec["students"]:
                    if (
                        rid.startswith("P")
                        and not rid.startswith("PR")
                        and rid not in visited
                    ):
                        queue.append(rid)

            if fetched % 25 == 0:
                print(
                    f"  fetched={fetched} kept={len(records)} queue={len(queue)} last={pid}",
                    flush=True,
                )
            time.sleep(args.sleep)

        print(f"\nFetched {fetched} persons, kept {len(records)} with place linkage.")

    # Sort: prefer records with birth_year, then by bdrc_id
    result = sorted(
        records.values(),
        key=lambda r: (r["birth_year"] is None, r["birth_year"] or 0, r["bdrc_id"]),
    )

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # Stats
    with_birth = sum(1 for r in result if r["birth_year"])
    with_death = sum(1 for r in result if r["death_year"])
    with_zh = sum(1 for r in result if r.get("name_zh"))
    with_en = sum(1 for r in result if r.get("name_en"))
    by_school = {}
    for r in result:
        s = r.get("school") or "unknown"
        by_school[s] = by_school.get(s, 0) + 1

    print()
    print(f"Saved {len(result)} BDRC persons -> {out_path}")
    print(f"  with name_zh: {with_zh}")
    print(f"  with name_en: {with_en}")
    print(f"  with birth_year: {with_birth}")
    print(f"  with death_year: {with_death}")
    print(f"  by school: {dict(sorted(by_school.items(), key=lambda kv: -kv[1]))}")

    # Key-person verification
    print()
    print("Key-person verification:")
    key_ids = {
        "P64": "Tsongkhapa",
        "P1649": "Dalai Lama 14",
        "P155": "Buton",
        "P1614": "Drakpa Gyaltsen",
        "P5089": "Sakya Pandita?",
        "P8205": "Padmasambhava?",
    }
    for pid, label in key_ids.items():
        hit = records.get(pid)
        if hit:
            print(
                f"  [x] {pid} {label}: {hit.get('name_zh') or hit.get('name_bo')}  "
                f"({hit['birth_year']}-{hit['death_year']}) @ {hit['primary_place']}"
            )
        else:
            print(f"  [ ] {pid} {label}: NOT in results")


if __name__ == "__main__":
    main()
