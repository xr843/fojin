#!/usr/bin/env python3
"""
Backfill person coordinates v2 - comprehensive approach:
1. Match temple/monastery names in description → use temple coords
2. Match ancient/modern city names → use city coords  
3. Match province names → use province capital coords
4. Match foreign place names → use country coords
All matches are A-grade (direct textual evidence).
"""
import asyncio, re, json

# Ancient city → modern coords (WGS84)
CITY_COORDS = {
    # 中国古都/名城
    '長安': (34.26, 108.94), '长安': (34.26, 108.94),
    '洛陽': (34.63, 112.45), '洛阳': (34.63, 112.45),
    '開封': (34.80, 114.31), '开封': (34.80, 114.31), '汴京': (34.80, 114.31), '汴梁': (34.80, 114.31),
    '杭州': (30.27, 120.15), '臨安': (30.27, 120.15), '临安': (30.27, 120.15),
    '南京': (32.06, 118.80), '建康': (32.06, 118.80), '金陵': (32.06, 118.80), '江寧': (32.06, 118.80),
    '北京': (39.91, 116.40), '燕京': (39.91, 116.40), '大都': (39.91, 116.40),
    '成都': (30.57, 104.07), '益州': (30.57, 104.07),
    '福州': (26.07, 119.30), '廣州': (23.13, 113.26), '广州': (23.13, 113.26),
    '蘇州': (31.30, 120.62), '苏州': (31.30, 120.62),
    '揚州': (32.39, 119.42), '扬州': (32.39, 119.42),
    '鎮江': (32.20, 119.45), '镇江': (32.20, 119.45), '潤州': (32.20, 119.45),
    '紹興': (30.00, 120.58), '绍兴': (30.00, 120.58), '會稽': (30.00, 120.58),
    '寧波': (29.87, 121.55), '宁波': (29.87, 121.55), '明州': (29.87, 121.55),
    '溫州': (28.00, 120.67), '温州': (28.00, 120.67),
    '泉州': (24.87, 118.68),
    '漳州': (24.51, 117.65),
    '潮州': (23.66, 116.62),
    '台州': (28.66, 121.42), '臺州': (28.66, 121.42),
    '湖州': (30.87, 120.09),
    '嘉興': (30.77, 120.75), '嘉兴': (30.77, 120.75),
    '常州': (31.81, 119.97),
    '無錫': (31.57, 120.30),
    '襄陽': (32.01, 112.14), '襄阳': (32.01, 112.14),
    '荊州': (30.33, 112.24), '荆州': (30.33, 112.24),
    '武昌': (30.57, 114.32),
    '長沙': (28.23, 112.94), '长沙': (28.23, 112.94), '潭州': (28.23, 112.94),
    '南昌': (28.68, 115.86), '洪州': (28.68, 115.86),
    '九江': (29.71, 116.00), '江州': (29.71, 116.00), '潯陽': (29.71, 116.00),
    '太原': (37.87, 112.55), '并州': (37.87, 112.55),
    '大同': (40.09, 113.30),
    '西安': (34.26, 108.94),
    '咸陽': (34.33, 108.71),
    '蘭州': (36.06, 103.83), '兰州': (36.06, 103.83),
    '敦煌': (40.14, 94.66),
    '涼州': (37.93, 102.64), '凉州': (37.93, 102.64), # 武威
    '瓜州': (40.52, 95.78),
    '拉薩': (29.65, 91.13), '拉萨': (29.65, 91.13),
    '昆明': (25.04, 102.68), '大理': (25.69, 100.18),
    '貴陽': (26.65, 106.63),
    '重慶': (29.56, 106.55), '重庆': (29.56, 106.55),
    # 佛教名山
    '天台': (29.14, 121.01), '天台山': (29.14, 121.01),
    '五臺': (39.08, 113.59), '五台': (39.08, 113.59), '五臺山': (39.08, 113.59), '五台山': (39.08, 113.59),
    '九華山': (30.49, 117.81), '九华山': (30.49, 117.81),
    '峨眉': (29.60, 103.33), '峨眉山': (29.60, 103.33), '峨嵋': (29.60, 103.33),
    '普陀': (30.01, 122.38), '普陀山': (30.01, 122.38),
    '雞足山': (25.97, 100.35), '鸡足山': (25.97, 100.35),
    '廬山': (29.56, 115.99), '庐山': (29.56, 115.99), '匡廬': (29.56, 115.99),
    '嵩山': (34.48, 113.07), '嵩岳': (34.48, 113.07),
    '終南山': (34.05, 108.95), '终南山': (34.05, 108.95), '終南': (34.05, 108.95),
    '雲居山': (29.24, 115.54), '云居山': (29.24, 115.54),
    '徑山': (30.39, 119.70), '径山': (30.39, 119.70),
    '靈隱': (30.24, 120.10), '灵隐': (30.24, 120.10),
    '少林': (34.51, 112.94), '少林寺': (34.51, 112.94),
    # 外国/古国
    '天竺': (28.61, 77.23), '印度': (28.61, 77.23), # New Delhi approx
    '罽賓': (34.53, 69.17), # Kapisa/Kabul area
    '龜茲': (41.72, 82.95), # Kucha
    '于闐': (37.12, 79.93), # Khotan
    '高麗': (37.57, 126.98), # Korea/Seoul
    '新羅': (35.84, 129.22), # Silla/Gyeongju
    '百濟': (36.48, 126.93), # Baekje/Buyeo
    '日本': (35.01, 135.77), # Kyoto
    '安息': (32.62, 44.42), # Parthia/Ctesiphon
    '大秦': (41.01, 28.98), # Rome/Constantinople
    '獅子國': (7.87, 80.77), '師子國': (7.87, 80.77), # Sri Lanka
    '爪哇': (-7.80, 110.36), # Java
    '占婆': (15.94, 108.06), # Champa
    '真臘': (13.36, 103.86), # Angkor
    '扶南': (11.56, 104.93), # Funan/Phnom Penh
    '交趾': (21.03, 105.85), '交州': (21.03, 105.85), # Vietnam/Hanoi
    '緬甸': (19.76, 96.07), # Myanmar
    '暹羅': (13.75, 100.52), # Siam/Bangkok
}

# Province name → capital coords
PROVINCE_COORDS = {
    '山西': (37.87, 112.55), '山東': (36.67, 116.98), '山东': (36.67, 116.98),
    '河南': (34.76, 113.65), '河北': (38.04, 114.51),
    '陝西': (34.26, 108.94), '陕西': (34.26, 108.94),
    '四川': (30.57, 104.07), '雲南': (25.04, 102.68), '云南': (25.04, 102.68),
    '浙江': (30.27, 120.15), '江蘇': (32.06, 118.80), '江苏': (32.06, 118.80),
    '福建': (26.07, 119.30), '廣東': (23.13, 113.26), '广东': (23.13, 113.26),
    '湖南': (28.23, 112.94), '湖北': (30.57, 114.32),
    '安徽': (31.82, 117.23), '江西': (28.68, 115.86),
    '貴州': (26.65, 106.63), '贵州': (26.65, 106.63),
    '甘肅': (36.06, 103.83), '甘肃': (36.06, 103.83),
    '青海': (36.62, 101.78), '西藏': (29.65, 91.13),
    '廣西': (22.82, 108.32), '广西': (22.82, 108.32),
    '海南': (20.02, 110.35),
    '遼寧': (41.80, 123.43), '辽宁': (41.80, 123.43),
    '吉林': (43.88, 125.32), '黑龍江': (45.75, 126.65),
    '內蒙': (40.82, 111.67), '寧夏': (38.47, 106.27),
    '新疆': (43.79, 87.60), '臺灣': (25.03, 121.57), '台灣': (25.03, 121.57),
}

async def main():
    import asyncpg
    conn = await asyncpg.connect('postgresql://fojin:FoJ1n_Pr0d_2026!sEcUrE@postgres:5432/fojin')
    
    # Get persons without coords but with description
    rows = await conn.fetch("""
        SELECT id, name_zh, description FROM kg_entities
        WHERE entity_type='person'
        AND ((properties->>'latitude') IS NULL OR (properties->>'latitude') = '')
        AND description IS NOT NULL AND description != ''
        ORDER BY id
    """)
    print(f'Persons without coords (with desc): {len(rows)}')
    
    # Get known monastery names → coords (only names >= 3 chars to avoid false matches)
    monasteries = await conn.fetch("""
        SELECT DISTINCT name_zh, 
               (properties->>'latitude')::float as lat,
               (properties->>'longitude')::float as lng
        FROM kg_entities 
        WHERE entity_type='monastery'
        AND (properties->>'latitude') IS NOT NULL AND (properties->>'latitude') != ''
        AND length(name_zh) >= 3
    """)
    temple_map = {}
    for m in monasteries:
        if m['name_zh'] not in temple_map:  # Keep first (avoid duplicates)
            temple_map[m['name_zh']] = (m['lat'], m['lng'])
    print(f'Known temples for matching: {len(temple_map)}')
    
    # Process each person
    updates = []
    stats = {'temple': 0, 'city': 0, 'province': 0, 'foreign': 0}
    
    for row in rows:
        desc = row['description']
        lat, lng, source = None, None, None
        
        # Priority 1: Match temple name in description (most specific)
        best_temple = None
        best_len = 0
        for tname, (tlat, tlng) in temple_map.items():
            if tname in desc and len(tname) > best_len:
                best_temple = tname
                best_len = len(tname)
                lat, lng = tlat, tlng
        if lat:
            source = f'desc_match:{best_temple}'
            stats['temple'] += 1
        
        # Priority 2: Match city names (sorted by length desc for best match)
        if not lat:
            for cname in sorted(CITY_COORDS.keys(), key=len, reverse=True):
                if cname in desc:
                    clat, clng = CITY_COORDS[cname]
                    lat, lng = clat, clng
                    source = f'city_match:{cname}'
                    stats['city'] += 1
                    break
        
        # Priority 3: Match province names
        if not lat:
            for pname in sorted(PROVINCE_COORDS.keys(), key=len, reverse=True):
                if pname in desc:
                    plat, plng = PROVINCE_COORDS[pname]
                    lat, lng = plat, plng
                    source = f'province_match:{pname}'
                    stats['province'] += 1
                    break
        
        if lat and lng:
            updates.append((row['id'], lat, lng, source))
    
    print(f'\nMatches found:')
    print(f'  Temple match: {stats["temple"]}')
    print(f'  City match: {stats["city"]}')
    print(f'  Province match: {stats["province"]}')
    print(f'  Total: {len(updates)}')
    
    # Show samples
    print(f'\nSamples:')
    import random
    for _, lat, lng, src in random.sample(updates, min(20, len(updates))):
        print(f'  {src} → ({lat:.2f}, {lng:.2f})')
    
    # Apply updates
    if updates:
        print(f'\nUpdating {len(updates)} persons...')
        async with conn.transaction():
            for eid, lat, lng, src in updates:
                await conn.execute("""
                    UPDATE kg_entities SET properties = 
                        COALESCE(properties::jsonb, '{}'::jsonb) || 
                        jsonb_build_object('latitude', $2::text::float, 'longitude', $3::text::float, 'geo_source', $4)
                    WHERE id = $1
                """, eid, lat, lng, src)
        print('Done!')
    
    # Final stats
    final = await conn.fetchval("""
        SELECT count(*) FROM kg_entities WHERE entity_type='person'
        AND (properties->>'latitude') IS NOT NULL AND (properties->>'latitude') != ''
    """)
    total = await conn.fetchval("SELECT count(*) FROM kg_entities WHERE entity_type='person'")
    print(f'\nPerson coords: {final}/{total} ({final*100//total}%)')
    
    await conn.close()

asyncio.run(main())
