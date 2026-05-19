"""Enrich Latin-script entity names with Chinese labels from Wikidata.

Input: backend/scripts/data/latin_entities.txt (pipe-separated dump)
Output: backend/scripts/data/name_zh_updates.json

Strategy:
1. For each entity, call Wikidata wbsearchentities API in English
2. Fetch candidate entities' coordinates and labels
3. Match if distance < 15km (monastery/place) or top-1 for person
4. Extract zh / zh-Hans / zh-Hant label

Rate limit: 1 req per 0.5s. ~7000 entities = ~60 min.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import requests

DATA_DIR = Path(__file__).parent / "data"
INPUT = DATA_DIR / "latin_entities.txt"
OUTPUT = DATA_DIR / "name_zh_updates.json"
PROGRESS = DATA_DIR / "name_zh_progress.json"

WD_API = "https://www.wikidata.org/w/api.php"
WD_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"

HEADERS = {"User-Agent": "FoJin-Research/1.0 (https://fojin.app; contact@fojin.app)"}
MAX_DIST_KM = 15.0


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def search_wikidata(name: str, lang: str = "en", limit: int = 5) -> list[dict]:
    try:
        r = requests.get(
            WD_API,
            params={
                "action": "wbsearchentities",
                "search": name,
                "language": lang,
                "format": "json",
                "limit": limit,
                "type": "item",
            },
            headers=HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        return r.json().get("search", [])
    except Exception as e:
        print(f"  search error: {e}", file=sys.stderr)
        return []


def fetch_entity(qid: str) -> dict | None:
    try:
        r = requests.get(WD_ENTITY.format(qid=qid), headers=HEADERS, timeout=15)
        r.raise_for_status()
        return r.json().get("entities", {}).get(qid)
    except Exception as e:
        print(f"  fetch error {qid}: {e}", file=sys.stderr)
        return None


def extract_zh_label(entity: dict) -> str | None:
    labels = entity.get("labels", {})
    for lang in ("zh-hans", "zh", "zh-cn", "zh-sg", "zh-hant", "zh-tw", "zh-hk"):
        if lang in labels:
            return labels[lang]["value"]
    return None


def extract_coords(entity: dict) -> tuple[float, float] | None:
    claims = entity.get("claims", {}).get("P625", [])
    for c in claims:
        val = c.get("mainsnak", {}).get("datavalue", {}).get("value", {})
        if "latitude" in val and "longitude" in val:
            return (val["latitude"], val["longitude"])
    return None


def load_entities() -> list[dict]:
    rows = []
    for line in INPUT.read_text().splitlines():
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) < 7:
            continue
        eid, etype, name_zh, name_en, country, lat, lng = parts[:7]
        rows.append({
            "id": int(eid),
            "entity_type": etype,
            "name": name_zh,
            "name_en": name_en,
            "country": country,
            "lat": float(lat) if lat else None,
            "lng": float(lng) if lng else None,
        })
    return rows


def load_progress() -> dict:
    if PROGRESS.exists():
        return json.loads(PROGRESS.read_text())
    return {"done_ids": [], "results": []}


def save_progress(state: dict) -> None:
    PROGRESS.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def main():
    entities = load_entities()
    state = load_progress()
    done = set(state["done_ids"])
    results = state["results"]

    print(f"Total: {len(entities)}, already done: {len(done)}")

    for i, ent in enumerate(entities):
        if ent["id"] in done:
            continue

        search_name = ent["name"]
        candidates = search_wikidata(search_name)
        time.sleep(0.4)

        matched = None
        for cand in candidates[:3]:
            qid = cand["id"]
            full = fetch_entity(qid)
            time.sleep(0.4)
            if not full:
                continue

            zh = extract_zh_label(full)
            if not zh:
                continue

            # Coordinate check for monastery/place
            if ent["entity_type"] in ("monastery", "place") and ent["lat"] is not None:
                coords = extract_coords(full)
                if coords is None:
                    continue
                dist = haversine(ent["lat"], ent["lng"], coords[0], coords[1])
                if dist > MAX_DIST_KM:
                    continue
                matched = {"id": ent["id"], "qid": qid, "name_zh": zh, "dist_km": round(dist, 2)}
                break
            else:
                matched = {"id": ent["id"], "qid": qid, "name_zh": zh}
                break

        if matched:
            results.append(matched)
            print(f"[{i+1}/{len(entities)}] ✓ {ent['id']} {search_name} → {matched['name_zh']}")
        else:
            print(f"[{i+1}/{len(entities)}] - {ent['id']} {search_name}")

        done.add(ent["id"])

        # Checkpoint every 25 entities
        if len(done) % 25 == 0:
            state["done_ids"] = list(done)
            state["results"] = results
            save_progress(state)

    state["done_ids"] = list(done)
    state["results"] = results
    save_progress(state)
    OUTPUT.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\nDone. Matched {len(results)}/{len(entities)}. Output: {OUTPUT}")


if __name__ == "__main__":
    main()
