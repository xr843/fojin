"""
Fetch Tibetan Buddhist places (monasteries, pilgrimage sites, monastic colleges)
from BDRC (Buddhist Digital Resource Center) via their public Linked Data endpoint.

Data source: https://ldspdi.bdrc.io/lib/placeGraph (public BDRC LDS-PDI templated query)
License: BDRC data is CC-BY 4.0 (per https://www.bdrc.io/copyright-and-license/)
Ontology: http://purl.bdrc.io/ontology/core/ (bdo:placeLat, bdo:placeLong, bdo:placeType)

This runs LOCALLY (not on the production server) to avoid IP rate-limiting on the server.
Output is written to backend/data/bdrc_places.json for the import step.

Strategy:
  - Seed with Wylie-transliteration names of famous Tibetan monasteries and sites.
  - For each seed, query the `placeGraph` lucene search template.
  - Deduplicate by BDRC G-ID, keep only results that have both placeLat and placeLong.
  - Keep only real monastic/pilgrimage place types (PT0037, PT0038, PT0040, PT0053, PT0064).
  - Extract multilingual labels (bo-x-ewts, zh-Hans, en).

Each record has:
    {
      "bdrc_id": "G108",
      "name_bo": "'bras spungs dgon/",   # Wylie transliteration
      "name_zh": "哲蚌寺",
      "name_en": "Drepung Monastery",
      "lat": 29.67623,
      "lng": 91.04701,
      "place_type": "PT0037",             # monastery | monastic college | ...
      "place_type_label": "monastery",
      "source": "bdrc",
      "source_url": "https://library.bdrc.io/show/bdr:G108"
    }

Usage:
    python scripts/fetch_bdrc_places.py
    python scripts/fetch_bdrc_places.py --out backend/data/bdrc_places.json
"""

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

BDRC_PLACE_GRAPH = "https://ldspdi.bdrc.io/lib/placeGraph"

# BDRC placeType codes we care about (Buddhist sites):
#   PT0037  dgon pa / monastery / 寺院
#   PT0038  bshad grwa / monastic college / 讲经院
#   PT0040  grwa tshang / monastic quarters / 扎仓
#   PT0053  gnas chen / pilgrimage site / 圣地
#   PT0064  sgrub grwa / retreat center / 闭关院
#   PT0050  temple
ALLOWED_PLACE_TYPES = {"PT0037", "PT0038", "PT0040", "PT0050", "PT0053", "PT0064"}

PLACE_TYPE_LABELS = {
    "PT0037": "monastery",
    "PT0038": "monastic college",
    "PT0040": "monastic quarters",
    "PT0050": "temple",
    "PT0053": "pilgrimage site",
    "PT0064": "retreat center",
}

# Seeds: famous Tibetan Buddhist monasteries and sites (Wylie transliteration
# as used by BDRC in `bo-x-ewts`). These cover all four major schools
# (Nyingma, Kagyu, Sakya, Gelug) plus Bon and Jonang, and the major pilgrimage sites.
# Source: standard reference works (Dorje's Tibet Handbook, Dowman's Power-Places of Central Tibet).
SEED_NAMES = [
    # Gelug (dGe-lugs) - six great monasteries
    "bras spungs",        # Drepung
    "se ra",              # Sera
    "dga' ldan",          # Ganden
    "bkra shis lhun po",  # Tashilhunpo
    "sku 'bum",           # Kumbum
    "bla brang bkra shis 'khyil",  # Labrang
    # Nyingma (rNying-ma) - six mother monasteries
    "bsam yas",           # Samye
    "smin grol gling",    # Mindroling
    "rdo rje brag",       # Dorje Drak
    "kaH thog",           # Katok
    "dpal yul",           # Palyul
    "rdzogs chen",        # Dzogchen
    "zhe chen",           # Shechen
    # Kagyu (bKa'-brgyud)
    "mtshur phu",         # Tsurphu
    "stag lung",          # Taklung
    "'bri gung",          # Drigung
    "mtshal gung thang",  # Tsal Gungtang
    "dpal spungs",        # Palpung
    "surmang",
    # Sakya (Sa-skya)
    "sa skya",            # Sakya
    "ngor e waM chos ldan",  # Ngor
    "tshar pa",           # Tsar
    # Jonang (Jo-nang)
    "jo nang",
    "dzam thang",
    # Bon (Bon-po)
    "sman ri",            # Menri
    "g.yung drung gling", # Yungdrungling
    # Central Tibet temples and pilgrimage sites
    "jo khang",           # Jokhang
    "ra mo che",          # Ramoche
    "ri bo che",          # Riwoche
    "rwa sgreng",         # Reting
    "rtsib ri",           # Tsibri
    "shel dkar chos sde", # Shekar Chode
    "rong phu",           # Rongphu (base of Everest)
    "tsha ri",            # Tsari pilgrimage
    "gangs ti se",        # Kailash
    "mtsho ma pham",      # Lake Manasarovar
    "chim phu",           # Chimpu
    "yer pa",             # Drak Yerpa
    "bsam yas mchims phu",
    # Kham and Amdo
    "ka thog",
    "sde dge dgon chen",  # Dege Gonchen
    "li thang",           # Lithang
    "rgyal rong",
    "a mchog",
    "rong bo",            # Rongwo / Rebgong
    # Bhutan and Himalayas
    "rta dbang",          # Tawang
    "sakya",
    "sikkim",
    "rum btegs",          # Rumtek
    # Historical and classical sites
    "bkra shis dge 'phel",
    "'bri khung mthil",
    "dwags lha sgam po",  # Daglha Gampo
    "gsang phu",          # Sangphu Neuthok
    "snar thang",         # Narthang
    "zhwa lu",            # Zhalu
]


def fetch_places_by_name(client: httpx.Client, name: str) -> dict:
    """Query BDRC placeGraph by Wylie name. Returns parsed JSON response."""
    try:
        r = client.get(
            BDRC_PLACE_GRAPH,
            params={"L_NAME": name, "LG_NAME": "bo-x-ewts"},
            timeout=60.0,
        )
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError as e:
        print(f"  HTTP error for {name!r}: {e}", file=sys.stderr)
        return {}
    except json.JSONDecodeError as e:
        print(f"  JSON decode error for {name!r}: {e}", file=sys.stderr)
        return {}


def extract_place_record(uri: str, preds: list) -> dict | None:
    """Extract a place record from a URI's predicate list. Returns None if no coords."""
    lat = lng = None
    name_bo = name_zh = name_en = None
    place_type = None
    alt_labels_bo = []

    for p in preds:
        t = p.get("type", "")
        v = p.get("value", "")
        lang = p.get("xml:lang", "")
        if t.endswith("/core/placeLat"):
            try:
                lat = float(v)
            except ValueError:
                pass
        elif t.endswith("/core/placeLong"):
            try:
                lng = float(v)
            except ValueError:
                pass
        elif t.endswith("/core/placeType"):
            place_type = v.rsplit("/", 1)[-1]
        elif t.endswith("skos/core#prefLabel"):
            if lang == "bo-x-ewts":
                name_bo = v
            elif lang == "zh-Hans":
                name_zh = v
            elif lang == "en":
                name_en = v
        elif t.endswith("skos/core#altLabel") and lang == "bo-x-ewts":
            alt_labels_bo.append(v)

    if lat is None or lng is None:
        return None
    if place_type not in ALLOWED_PLACE_TYPES:
        return None
    # Sanity-check coords are in plausible Tibetan/Himalayan range
    # (wider bounds to tolerate Mongolia, Bhutan, Nepal, India monasteries)
    if not (15 <= lat <= 55 and 60 <= lng <= 120):
        return None

    bdrc_id = uri.rsplit("/", 1)[-1]
    return {
        "bdrc_id": bdrc_id,
        "name_bo": name_bo,
        "name_zh": name_zh,
        "name_en": name_en,
        "alt_labels_bo": alt_labels_bo,
        "lat": lat,
        "lng": lng,
        "place_type": place_type,
        "place_type_label": PLACE_TYPE_LABELS.get(place_type, place_type),
        "source": "bdrc",
        "source_url": f"https://library.bdrc.io/show/bdr:{bdrc_id}",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[1] / "data" / "bdrc_places.json"),
    )
    parser.add_argument("--sleep", type=float, default=0.8, help="delay between queries (sec)")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    places_by_id: dict[str, dict] = {}
    print(f"Querying BDRC for {len(SEED_NAMES)} seed names...", flush=True)

    with httpx.Client(headers={"User-Agent": "FoJin/1.0 (buddhist digital humanities)"}) as client:
        for i, name in enumerate(SEED_NAMES, 1):
            data = fetch_places_by_name(client, name)
            main_g = data.get("main", {})
            hits = 0
            for uri, preds in main_g.items():
                rec = extract_place_record(uri, preds)
                if not rec:
                    continue
                if rec["bdrc_id"] in places_by_id:
                    # Merge labels (latest seed may have found new name variants)
                    old = places_by_id[rec["bdrc_id"]]
                    for k in ("name_bo", "name_zh", "name_en"):
                        if not old.get(k) and rec.get(k):
                            old[k] = rec[k]
                    continue
                places_by_id[rec["bdrc_id"]] = rec
                hits += 1
            print(
                f"  [{i:2d}/{len(SEED_NAMES)}] {name!r:40s} -> {hits:3d} new w/coords "
                f"(total={len(places_by_id)})",
                flush=True,
            )
            time.sleep(args.sleep)

    records = sorted(places_by_id.values(), key=lambda r: r["bdrc_id"])
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    # Quick stats
    with_zh = sum(1 for r in records if r.get("name_zh"))
    with_en = sum(1 for r in records if r.get("name_en"))
    by_type: dict[str, int] = {}
    for r in records:
        by_type[r["place_type_label"]] = by_type.get(r["place_type_label"], 0) + 1

    print()
    print(f"Saved {len(records)} BDRC places with coords -> {out_path}")
    print(f"  with name_zh: {with_zh}")
    print(f"  with name_en: {with_en}")
    print(f"  by type: {by_type}")


if __name__ == "__main__":
    main()
