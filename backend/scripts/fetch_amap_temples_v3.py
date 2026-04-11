"""Fetch Chinese Buddhist temples from Amap - V3 city-level search.

V2 searched by province (31 queries × 7 keywords), hitting the 500-result-per-query cap.
V3 searches by every prefecture-level city (~340 cities) to avoid truncation.

Uses Amap's administrative district API to get all city codes first,
then searches each city for Buddhist temples.

Rate limit: 5000 calls/day (free key). ~340 cities × 3 keywords × 2 pages avg = ~2000 calls.
"""
import json, math, time, os, sys
import urllib.parse, urllib.request

AMAP_KEY = os.environ.get("AMAP_KEY")
if not AMAP_KEY:
    sys.exit("ERROR: AMAP_KEY environment variable is not set (check .env)")
OUTPUT = "data/amap_temples_v3.json"
PROGRESS_FILE = "data/amap_v3_progress.json"

KEYWORDS = ["寺", "庵", "禅寺"]
SKIP_WORDS = ["清真", "教堂", "基督", "天主", "道观", "道教", "伊斯兰",
              "关帝", "妈祖", "城隍", "土地庙", "孔庙", "文庙",
              "殡仪", "墓", "陵园", "寺沟", "寺坪", "寺河",
              "寺前", "寺后", "寺湾"]

def gcj02_to_wgs84(lng, lat):
    a = 6378245.0; ee = 0.00669342162296594323
    x = lng - 105.0; y = lat - 35.0
    dlat = -100+2*x+3*y+0.2*y*y+0.1*x*y+0.2*math.sqrt(abs(x))
    dlat += (20*math.sin(6*x*math.pi)+20*math.sin(2*x*math.pi))*2/3
    dlat += (20*math.sin(y*math.pi)+40*math.sin(y/3*math.pi))*2/3
    dlat += (160*math.sin(y/12*math.pi)+320*math.sin(y*math.pi/30))*2/3
    dlng = 300+x+2*y+0.1*x*x+0.1*x*y+0.1*math.sqrt(abs(x))
    dlng += (20*math.sin(6*x*math.pi)+20*math.sin(2*x*math.pi))*2/3
    dlng += (20*math.sin(x*math.pi)+40*math.sin(x/3*math.pi))*2/3
    dlng += (150*math.sin(x/12*math.pi)+300*math.sin(x/30*math.pi))*2/3
    radlat = lat/180*math.pi
    magic = 1-ee*math.sin(radlat)**2
    sqm = math.sqrt(magic)
    dlat = dlat*180/((a*(1-ee))/(magic*sqm)*math.pi)
    dlng = dlng*180/(a/sqm*math.cos(radlat)*math.pi)
    return lng-dlng, lat-dlat

def api_call(url):
    req = urllib.request.Request(url, headers={"User-Agent": "FoJinBot/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

def get_all_cities():
    """Get all prefecture-level cities from Amap district API."""
    params = urllib.parse.urlencode({
        'key': AMAP_KEY,
        'keywords': '中国',
        'subdistrict': 2,
        'extensions': 'base',
    })
    url = f"https://restapi.amap.com/v3/config/district?{params}"
    data = api_call(url)
    cities = []
    if data.get('status') == '1':
        for province in data['districts'][0].get('districts', []):
            pname = province['name']
            for city in province.get('districts', []):
                cities.append({
                    'name': city['name'],
                    'adcode': city.get('adcode', ''),
                    'province': pname,
                })
    return cities

def search_city(keyword, city_name, page=1):
    params = urllib.parse.urlencode({
        'key': AMAP_KEY,
        'keywords': keyword,
        'city': city_name,
        'citylimit': 'true',
        'offset': 20,
        'page': page,
        'output': 'json',
        'extensions': 'base',
    })
    return api_call(f"https://restapi.amap.com/v3/place/text?{params}")

def main():
    # Load progress if resuming
    progress = {}
    all_pois = {}
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            progress = json.load(f)
        all_pois = progress.get('pois', {})
        done_cities = set(progress.get('done_cities', []))
        print(f'Resuming: {len(done_cities)} cities done, {len(all_pois)} POIs found')
    else:
        done_cities = set()

    # Get city list
    print('Getting city list...')
    cities = get_all_cities()
    print(f'Found {len(cities)} prefecture-level cities')
    time.sleep(0.5)

    total_requests = 1  # district API call
    daily_limit = 4800  # leave 200 for other uses

    for ci, city in enumerate(cities):
        cname = city['name']
        if cname in done_cities:
            continue

        city_count = 0
        for keyword in KEYWORDS:
            page = 1
            while page <= 25:
                if total_requests >= daily_limit:
                    print(f'\nApproaching daily limit ({total_requests} requests). Saving progress...')
                    progress = {
                        'pois': all_pois,
                        'done_cities': list(done_cities),
                        'total_requests': total_requests,
                    }
                    with open(PROGRESS_FILE, 'w') as f:
                        json.dump(progress, f, ensure_ascii=False)
                    # Also save current results
                    with open(OUTPUT, 'w') as f:
                        json.dump(list(all_pois.values()), f, ensure_ascii=False, indent=2)
                    print(f'Saved {len(all_pois)} POIs. Will resume tomorrow.')
                    return

                try:
                    data = search_city(keyword, cname, page)
                    total_requests += 1
                    time.sleep(0.35)
                except Exception as e:
                    if 'OVER_LIMIT' in str(e) or '10044' in str(e):
                        print(f'\nDaily limit reached! Saving...')
                        progress = {'pois': all_pois, 'done_cities': list(done_cities), 'total_requests': total_requests}
                        with open(PROGRESS_FILE, 'w') as f:
                            json.dump(progress, f, ensure_ascii=False)
                        with open(OUTPUT, 'w') as f:
                            json.dump(list(all_pois.values()), f, ensure_ascii=False, indent=2)
                        return
                    print(f'  ERROR {cname}/{keyword} p{page}: {e}')
                    time.sleep(2)
                    break

                if data.get('status') != '1':
                    info = data.get('info', '')
                    if 'OVER_LIMIT' in info:
                        print(f'\nDaily limit! Saving...')
                        progress = {'pois': all_pois, 'done_cities': list(done_cities), 'total_requests': total_requests}
                        with open(PROGRESS_FILE, 'w') as f:
                            json.dump(progress, f, ensure_ascii=False)
                        with open(OUTPUT, 'w') as f:
                            json.dump(list(all_pois.values()), f, ensure_ascii=False, indent=2)
                        return
                    break

                pois = data.get('pois', [])
                if not pois:
                    break

                for poi in pois:
                    pid = poi.get('id', '')
                    name = poi.get('name', '')
                    location = poi.get('location', '')
                    if not pid or not name or not location:
                        continue
                    if any(w in name for w in SKIP_WORDS):
                        continue
                    if pid in all_pois:
                        continue
                    try:
                        lng_g, lat_g = [float(x) for x in location.split(',')]
                        lng_w, lat_w = gcj02_to_wgs84(lng_g, lat_g)
                    except:
                        continue

                    all_pois[pid] = {
                        'amap_id': pid,
                        'name': name,
                        'latitude': round(lat_w, 7),
                        'longitude': round(lng_w, 7),
                        'address': poi.get('address', ''),
                        'province': poi.get('pname', city['province']),
                        'city': poi.get('cityname', cname),
                        'district': poi.get('adname', ''),
                        'type': poi.get('type', ''),
                        'typecode': poi.get('typecode', ''),
                    }
                    city_count += 1

                count = int(data.get('count', 0))
                if page * 20 >= count or page * 20 >= 500:
                    break
                page += 1

        done_cities.add(cname)
        if ci % 20 == 0:
            print(f'[{ci+1}/{len(cities)}] {cname}: +{city_count}, total: {len(all_pois)}, requests: {total_requests}')

    # Final save
    result = list(all_pois.values())
    with open(OUTPUT, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f'\nComplete! {len(result)} POIs, {total_requests} requests')

    # Cleanup progress file
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)

if __name__ == '__main__':
    main()
