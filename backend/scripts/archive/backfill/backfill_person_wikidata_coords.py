#!/usr/bin/env python3
"""Backfill person coordinates from Wikidata API (wbgetentities)."""
import json, time, subprocess, urllib.request

DB_CMD = ["docker", "compose", "exec", "-T", "postgres", "psql", "-U", "fojin", "-d", "fojin", "-t", "-A"]
API_URL = "https://www.wikidata.org/w/api.php"
UA = "FoJinBot/1.0 (https://fojin.app)"
BATCH_SIZE = 50

def db_query(sql):
    r = subprocess.Popen(DB_CMD + ["-c", sql], stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd="/home/admin/fojin")
    out, _ = r.communicate()
    return [line for line in out.decode().strip().split("\n") if line]

def db_exec(sql):
    r = subprocess.Popen(DB_CMD + ["-c", sql], stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd="/home/admin/fojin")
    out, _ = r.communicate()
    return out.decode().strip()

def wbget(ids, props="claims"):
    url = "{}?action=wbgetentities&ids={}&props={}&format=json".format(API_URL, "|".join(ids), props)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read().decode()).get("entities", {})

PLACE_PROPS = [("P19", "wikidata:P19"), ("P937", "wikidata:P937"), ("P20", "wikidata:P20")]
PRIORITY = {"wikidata:P19": 0, "wikidata:P937": 1, "wikidata:P20": 2}

# Step 1: Get persons
rows = db_query(
    "SELECT id || '|' || (external_ids->>'wikidata') FROM kg_entities "
    "WHERE entity_type='person' AND (properties->>'latitude') IS NULL "
    "AND external_ids->>'wikidata' IS NOT NULL"
)
entities = {}
for row in rows:
    parts = row.split("|")
    entities[parts[1]] = int(parts[0])
print("Found {} persons".format(len(entities)))

# Step 2: Get place QIDs for each person
person_places = {}  # qid -> (place_qid, source)
qids = list(entities.keys())
for i in range(0, len(qids), BATCH_SIZE):
    batch = qids[i:i+BATCH_SIZE]
    print("Fetching persons batch {} ...".format(i//BATCH_SIZE + 1))
    try:
        data = wbget(batch)
        for qid, entity in data.items():
            claims = entity.get("claims", {})
            for prop, source in PLACE_PROPS:
                if prop in claims:
                    try:
                        place_id = claims[prop][0]["mainsnak"]["datavalue"]["value"]["id"]
                        if qid not in person_places or PRIORITY[source] < PRIORITY.get(person_places[qid][1], 9):
                            person_places[qid] = (place_id, source)
                    except (KeyError, IndexError):
                        pass
    except Exception as e:
        print("  Error: {}".format(e))
    time.sleep(1)

print("Found {} persons with place references".format(len(person_places)))

# Step 3: Get coordinates for all unique places
unique_places = list(set(p[0] for p in person_places.values()))
place_coords = {}  # place_qid -> (lat, lng)
for i in range(0, len(unique_places), BATCH_SIZE):
    batch = unique_places[i:i+BATCH_SIZE]
    print("Fetching place coords batch {} ...".format(i//BATCH_SIZE + 1))
    try:
        data = wbget(batch)
        for pid, entity in data.items():
            claims = entity.get("claims", {})
            if "P625" in claims:
                try:
                    coord = claims["P625"][0]["mainsnak"]["datavalue"]["value"]
                    place_coords[pid] = (coord["latitude"], coord["longitude"])
                except (KeyError, IndexError):
                    pass
    except Exception as e:
        print("  Error: {}".format(e))
    time.sleep(1)

print("Got coordinates for {} places".format(len(place_coords)))

# Step 4: Update DB
updated = 0
for qid, (place_id, source) in person_places.items():
    if place_id not in place_coords:
        continue
    lat, lng = place_coords[place_id]
    eid = entities[qid]
    payload = json.dumps({"latitude": lat, "longitude": lng, "geo_source": source})
    sql = "UPDATE kg_entities SET properties = (properties::jsonb || '{}'::jsonb)::json WHERE id = {} AND (properties->>'latitude') IS NULL".format(payload, eid)
    out = db_exec(sql)
    if "UPDATE 1" in out:
        updated += 1

print("\nDone! Updated {} persons with coordinates.".format(updated))
