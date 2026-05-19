#!/usr/bin/env python3
"""Backfill person coordinates from description place name matching."""
import json
import re
import subprocess
import sys

ANCIENT_PLACES = {
    "長安": (34.26, 108.94), "洛陽": (34.63, 112.45), "洛阳": (34.63, 112.45),
    "建康": (32.06, 118.80), "金陵": (32.06, 118.80), "江陵": (30.35, 112.19),
    "成都": (30.57, 104.07), "杭州": (30.25, 120.17), "蘇州": (31.30, 120.58),
    "揚州": (32.39, 119.41), "廣州": (23.13, 113.26), "福州": (26.07, 119.30),
    "開封": (34.80, 114.30), "天台": (29.14, 121.01), "廬山": (29.56, 115.97),
    "五台山": (39.08, 113.55), "峨眉山": (29.60, 103.33), "普陀山": (30.00, 122.38),
    "九華山": (30.48, 117.80), "少林寺": (34.51, 112.94), "嵩山": (34.49, 112.95),
    "曹溪": (24.70, 113.60), "黃梅": (30.07, 115.94), "廬陵": (27.11, 114.98),
    "潭州": (28.23, 112.94), "越州": (30.00, 120.58), "明州": (29.87, 121.55),
    "台州": (28.66, 121.42), "婺州": (29.08, 119.65), "饒州": (29.00, 116.68),
    "吉州": (27.11, 114.98), "袁州": (27.80, 114.38), "撫州": (27.95, 116.36),
    "汝州": (33.95, 112.84), "許州": (34.02, 113.85), "鄧州": (32.69, 112.09),
    "襄陽": (32.01, 112.14), "荊州": (30.35, 112.19), "澧州": (29.43, 111.76),
    "岳州": (29.37, 113.09), "鼎州": (29.04, 111.69), "衡州": (26.89, 112.57),
    "韶州": (24.81, 113.60), "泉州": (24.87, 118.68), "漳州": (24.51, 117.65),
    "溫州": (28.00, 120.67), "處州": (28.45, 119.92), "湖州": (30.87, 120.09),
    "嘉興": (30.77, 120.76), "紹興": (30.00, 120.58), "寧波": (29.87, 121.55),
    "瑞州": (28.38, 115.55), "隆興": (28.68, 115.89), "臨安": (30.23, 119.72),
    "大梁": (34.80, 114.30), "汴京": (34.80, 114.30), "汴梁": (34.80, 114.30),
    "燕京": (39.91, 116.39), "北京": (39.91, 116.39), "南京": (32.06, 118.80),
    "印度": (25.27, 83.01), "天竺": (25.27, 83.01), "摩竭陀": (25.00, 85.42),
    "迦濕彌羅": (34.08, 74.79), "犍陀羅": (34.17, 71.83),
    "西域": (40.00, 76.00), "龜茲": (41.73, 82.97), "于闐": (37.12, 79.93),
    "高麗": (37.57, 126.98), "百濟": (36.48, 126.93), "新羅": (35.84, 129.22),
    "日本": (35.68, 139.69), "奈良": (34.68, 135.80), "京都": (35.01, 135.77),
    "暹羅": (13.75, 100.52), "緬甸": (19.76, 96.07), "錫蘭": (7.87, 80.77),
    "拉薩": (29.65, 91.13), "西藏": (29.65, 91.13),
}

def psql(sql):
    """Run SQL via docker compose exec."""
    cmd = [
        "docker", "compose", "exec", "-T", "postgres",
        "psql", "-U", "fojin", "-d", "fojin",
        "-t", "-A", "-c", sql
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, cwd="/home/admin/fojin")
    if result.returncode != 0:
        print(f"SQL error: {result.stderr}", file=sys.stderr)
        return ""
    return result.stdout.strip()

def main():
    # 1. Build place name -> coords from DB places
    print("Loading place entities from DB...")
    rows = psql(
        "SELECT name_zh, properties->>'latitude', properties->>'longitude' "
        "FROM kg_entities WHERE entity_type='place' "
        "AND properties->>'latitude' IS NOT NULL"
    )
    db_places = {}
    for line in rows.split("\n"):
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) == 3:
            name, lat, lng = parts[0].strip(), parts[1].strip(), parts[2].strip()
            if name and lat and lng:
                try:
                    db_places[name] = (float(lat), float(lng))
                except ValueError:
                    pass
    print(f"  DB places: {len(db_places)}")

    # 2. Merge: DB places + ancient places (DB takes priority)
    all_places = dict(ANCIENT_PLACES)
    all_places.update(db_places)
    print(f"  Total place names: {len(all_places)}")

    # Sort by length descending for longest-match-first
    sorted_names = sorted(all_places.keys(), key=len, reverse=True)
    # Build regex pattern
    pattern = re.compile("|".join(re.escape(n) for n in sorted_names))

    # 3. Get persons without coords
    print("Loading persons without coordinates...")
    rows = psql(
        "SELECT id, description FROM kg_entities "
        "WHERE entity_type='person' AND description IS NOT NULL "
        "AND description != '' AND (properties->>'latitude' IS NULL)"
    )

    updated = 0
    no_match = 0
    persons = []
    for line in rows.split("\n"):
        if not line.strip():
            continue
        idx = line.find("|")
        if idx < 0:
            continue
        pid = line[:idx].strip()
        desc = line[idx+1:]
        persons.append((pid, desc))

    print(f"  Persons to process: {len(persons)}")

    # 4. Match and update
    updates = []
    for pid, desc in persons:
        m = pattern.search(desc)
        if m:
            place_name = m.group()
            lat, lng = all_places[place_name]
            updates.append((pid, lat, lng, place_name))
        else:
            no_match += 1

    print(f"  Matched: {len(updates)}, No match: {no_match}")

    # Batch update via single SQL
    if updates:
        print("Updating database...")
        # Build a single UPDATE using VALUES
        cases_lat = []
        cases_lng = []
        cases_geo = []
        ids = []
        for pid, lat, lng, pname in updates:
            safe_name = pname.replace("'", "''")
            cases_lat.append(f"WHEN id={pid} THEN {lat}")
            cases_lng.append(f"WHEN id={pid} THEN {lng}")
            cases_geo.append(f"WHEN id={pid} THEN 'place_match:{safe_name}'")
            ids.append(pid)

        # Do in batches of 200
        batch_size = 200
        for i in range(0, len(updates), batch_size):
            batch = updates[i:i+batch_size]
            batch_ids = [u[0] for u in batch]
            set_parts = []
            for pid, lat, lng, pname in batch:
                safe_name = pname.replace("'", "''")
                set_parts.append(
                    f"UPDATE kg_entities SET properties = "
                    f"COALESCE(properties, '{{}}'::json)::jsonb || "
                    f"jsonb_build_object('latitude', {lat}, 'longitude', {lng}, "
                    f"'geo_source', 'place_match:{safe_name}') "
                    f"WHERE id = {pid};"
                )
            sql = " ".join(set_parts)
            psql(sql)
            updated += len(batch)
            print(f"  Updated batch {i//batch_size + 1}: {len(batch)} records")

    print(f"\nDone! Updated {updated} persons, {no_match} had no place match.")

    # Show top matched places
    from collections import Counter
    place_counts = Counter(u[3] for u in updates)
    print("\nTop 20 matched places:")
    for name, count in place_counts.most_common(20):
        print(f"  {name}: {count}")

if __name__ == "__main__":
    main()
