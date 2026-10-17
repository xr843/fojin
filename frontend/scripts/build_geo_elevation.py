#!/usr/bin/env python3
"""给 /map 的 3D 地形模式预取每个地理实体的海拔，写入 public/elevation/kg-geo-elev.json。

为什么离线：3D 模式要把点画在地形表面（z = 海拔 × 夸张系数）。在浏览器里对 6.5 万个点逐个
调 map.queryTerrainElevation 实测要 3–5 秒、且未加载瓦片处返回 0。高程源与地图渲染用的
完全相同（MapTiler terrain-rgb-v2），z9（512px 瓦片，约 150 m/像素）双线性采样。

不在这份文件里的实体（之后新增的）由前端在 3D 下按需用 queryTerrainElevation 兜底。

用法：python3 scripts/build_geo_elevation.py [--api https://fojin.app] [--out public/elevation/kg-geo-elev.json]
MapTiler key 限定来源，请求需带 fojin.app 的 Referer。
"""
import argparse
import io
import json
import math
import sys
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

KEY = "sBS5GCqJuftwymqkp64I"  # 与 DeckGLMap.tsx 同一把公开前端 key
Z = 9
TILE = 512
HEADERS = {"Referer": "https://fojin.app/", "Origin": "https://fojin.app", "User-Agent": "Mozilla/5.0 fojin-elev-build"}


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def world_px(lat: float, lng: float) -> tuple[float, float]:
    n = 2**Z * TILE
    x = (lng + 180) / 360 * n
    s = math.sin(math.radians(max(min(lat, 85.0511), -85.0511)))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return x, y


def decode(px) -> float:
    r, g, b = px[:3]
    return -10000 + (r * 65536 + g * 256 + b) * 0.1


def sample(img, fx: float, fy: float) -> float:
    # 双线性；像素中心在 +0.5，边缘夹紧到瓦片内
    fx = min(max(fx - 0.5, 0), TILE - 1.001)
    fy = min(max(fy - 0.5, 0), TILE - 1.001)
    x0, y0 = int(fx), int(fy)
    dx, dy = fx - x0, fy - y0
    e00 = decode(img.getpixel((x0, y0)))
    e10 = decode(img.getpixel((x0 + 1, y0)))
    e01 = decode(img.getpixel((x0, y0 + 1)))
    e11 = decode(img.getpixel((x0 + 1, y0 + 1)))
    return (e00 * (1 - dx) + e10 * dx) * (1 - dy) + (e01 * (1 - dx) + e11 * dx) * dy


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="https://fojin.app")
    ap.add_argument("--out", default="public/elevation/kg-geo-elev.json")
    args = ap.parse_args()

    ents = json.loads(get(f"{args.api}/api/kg/geo?limit=80000"))["entities"]
    by_tile: dict[tuple[int, int], list[tuple[int, float, float]]] = defaultdict(list)
    for e in ents:
        x, y = world_px(e["latitude"], e["longitude"])
        tx, ty = int(x // TILE), int(y // TILE)
        by_tile[(tx, ty)].append((e["id"], x - tx * TILE, y - ty * TILE))
    print(f"{len(ents)} entities, {len(by_tile)} z{Z} tiles", file=sys.stderr)

    out: dict[str, int] = {}
    failed = 0

    def work(item):
        (tx, ty), pts = item
        url = f"https://api.maptiler.com/tiles/terrain-rgb-v2/{Z}/{tx}/{ty}.webp?key={KEY}"
        for attempt in range(3):
            try:
                img = Image.open(io.BytesIO(get(url))).convert("RGB")
                return [(i, sample(img, fx, fy)) for i, fx, fy in pts]
            except Exception as exc:  # noqa: BLE001 — 网络抖动重试，最后一次仍失败则整块跳过
                err = exc
        print(f"tile {tx},{ty} failed: {err}", file=sys.stderr)
        return None

    done = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        for res in pool.map(work, by_tile.items()):
            done += 1
            if res is None:
                failed += 1
                continue
            for i, elev in res:
                # 海面以下（填海、湖面编码噪声）一律按 0：点画在水面上，不沉下去
                out[str(i)] = max(0, round(elev))
            if done % 200 == 0:
                print(f"{done}/{len(by_tile)} tiles", file=sys.stderr)

    # 紧凑格式（仓库限制单文件 ≤500 KB）：id 升序存差分，海拔以 10 m 为单位取整。
    # 10 m 的取整误差在 z11、夸张 1.6 倍下不到 0.3 px。前端解码见 DeckGLMap.tsx decodeElevations。
    ids = sorted(int(k) for k in out)
    payload = {
        "v": 1,
        "unit_m": 10,
        "id_delta": [ids[0]] + [b - a for a, b in zip(ids, ids[1:])] if ids else [],
        "elev": [round(out[str(i)] / 10) for i in ids],
    }
    with open(args.out, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    print(f"wrote {len(out)} elevations to {args.out}; failed tiles: {failed}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
