"""Import Amap V3 temples into kg_entities, skipping duplicates."""
import asyncio, json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

async def main():
    import asyncpg
    DB = os.environ.get('DATABASE_URL', 'postgresql://fojin:FoJ1n_Pr0d_2026!sEcUrE@postgres:5432/fojin')
    conn = await asyncpg.connect(DB)

    # Load data
    with open('data/amap_temples_v3.json', encoding='utf-8') as f:
        pois = json.load(f)
    print(f'Loaded {len(pois)} POIs from amap_temples_v3.json')

    # Get existing amap IDs to skip
    existing = set()
    rows = await conn.fetch(
        """SELECT external_ids->>'amap' as aid FROM kg_entities 
           WHERE entity_type='monastery' AND external_ids ? 'amap'"""
    )
    for r in rows:
        if r['aid']:
            existing.add(r['aid'])
    print(f'Existing amap IDs in DB: {len(existing)}')

    # Also check by name+coords to avoid near-duplicates
    coord_names = set()
    rows2 = await conn.fetch(
        """SELECT name_zh, round((properties->>'latitude')::numeric, 4) as lat,
                  round((properties->>'longitude')::numeric, 4) as lng
           FROM kg_entities WHERE entity_type='monastery' AND properties->>'country'='CN'"""
    )
    for r in rows2:
        if r['lat'] and r['lng']:
            coord_names.add((r['name_zh'], float(r['lat']), float(r['lng'])))
    print(f'Existing name+coord combos: {len(coord_names)}')

    inserted = 0
    skipped_existing = 0
    skipped_dup = 0

    for poi in pois:
        aid = poi['amap_id']
        if aid in existing:
            skipped_existing += 1
            continue

        name = poi['name']
        lat = round(poi['latitude'], 4)
        lng = round(poi['longitude'], 4)
        if (name, lat, lng) in coord_names:
            skipped_dup += 1
            continue

        props = json.dumps({
            'latitude': poi['latitude'],
            'longitude': poi['longitude'],
            'geo_source': f'amap:CN',
            'country': 'CN',
            'province': poi.get('province', ''),
            'city': poi.get('city', ''),
            'district': poi.get('district', ''),
            'address': poi.get('address', ''),
        }, ensure_ascii=False)

        ext_ids = json.dumps({'amap': aid}, ensure_ascii=False)

        await conn.execute(
            """INSERT INTO kg_entities (entity_type, name_zh, properties, external_ids)
               VALUES ('monastery', \, \::jsonb, \::jsonb)""",
            name, props, ext_ids
        )
        inserted += 1
        coord_names.add((name, lat, lng))
        existing.add(aid)

    print(f'\nInserted: {inserted}')
    print(f'Skipped (existing amap ID): {skipped_existing}')
    print(f'Skipped (duplicate name+coords): {skipped_dup}')

    total = await conn.fetchval(
        "SELECT count(*) FROM kg_entities WHERE entity_type='monastery' AND properties->>'country'='CN'"
    )
    print(f'Total CN monasteries now: {total}')

    await conn.close()

asyncio.run(main())
