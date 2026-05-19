"""
Download SuttaCentral data locally for offline import.

Uses suttaplex API to enumerate individual suttas from each nikaya,
then downloads Pali root + English translation for each.

Saves everything as JSON files in data/sc_download/
"""

import asyncio
import json
import os
import sys
import time

import httpx

SC_API_BASE = "https://suttacentral.net/api"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sc_download")
RATE_LIMIT = 0.4  # seconds between requests
CHECKPOINT_FILE = os.path.join(OUTPUT_DIR, "_checkpoint.json")

# Major Pali canon sections to enumerate via suttaplex
NIKAYA_SECTIONS = [
    "dn", "mn", "sn", "an",          # 4 main nikayas
    "kp", "dhp", "ud", "iti", "snp",  # Khuddaka Nikaya texts
    "vv", "pv", "thag", "thig",       # verses
    "ja",                              # Jataka
    "ne", "cnd", "mnd", "ps",         # commentary-like
    "mil",                             # Milindapanha
    "pli-tv-bu-vb", "pli-tv-bi-vb",   # Vinaya
    "pli-tv-kd", "pli-tv-pvr",
    "dn-a", "mn-a", "sn-a", "an-a",   # Atthakatha
]


def load_checkpoint() -> dict:
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {}


def save_checkpoint(data: dict):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(data, f)


async def discover_suttas(client: httpx.AsyncClient) -> list[dict]:
    """Use suttaplex API to discover all individual suttas."""
    catalog_file = os.path.join(OUTPUT_DIR, "catalog.json")
    if os.path.exists(catalog_file):
        with open(catalog_file) as f:
            catalog = json.load(f)
        print(f"  Loaded existing catalog: {len(catalog)} suttas")
        return catalog

    all_suttas = []
    seen = set()

    for section in NIKAYA_SECTIONS:
        try:
            await asyncio.sleep(RATE_LIMIT)
            resp = await client.get(f"{SC_API_BASE}/suttaplex/{section}")
            if resp.status_code != 200:
                print(f"  {section}: HTTP {resp.status_code}")
                continue

            data = resp.json()
            if not isinstance(data, list):
                continue

            leaves = [d for d in data if d.get("type") == "leaf" and d.get("uid")]
            for leaf in leaves:
                uid = leaf["uid"]
                if uid not in seen:
                    seen.add(uid)
                    all_suttas.append({
                        "uid": uid,
                        "original_title": leaf.get("original_title", ""),
                        "translated_title": leaf.get("translated_title", ""),
                        "acronym": leaf.get("acronym", ""),
                    })

            print(f"  {section}: {len(leaves)} leaves (total: {len(all_suttas)})")

        except Exception as e:
            print(f"  {section}: error - {e}")

    # Save catalog
    with open(catalog_file, "w") as f:
        json.dump(all_suttas, f, ensure_ascii=False, indent=1)

    print(f"  Total suttas discovered: {len(all_suttas)}")
    return all_suttas


async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    content_dir = os.path.join(OUTPUT_DIR, "content")
    os.makedirs(content_dir, exist_ok=True)

    checkpoint = load_checkpoint()

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        # Phase 1: Discover suttas
        print("[Phase 1] Discovering suttas via suttaplex API...")
        suttas = await discover_suttas(client)

        if not suttas:
            print("No suttas found!")
            return

        # Phase 2: Download content
        print(f"\n[Phase 2] Downloading content for {len(suttas)} suttas...")
        last_idx = checkpoint.get("last_content_idx", -1)
        downloaded = 0
        skipped = 0
        errors = 0
        no_content = 0
        start = time.time()

        for i, sutta in enumerate(suttas):
            if i <= last_idx:
                skipped += 1
                continue

            uid = sutta["uid"]
            safe_uid = uid.replace("/", "_")
            out_file = os.path.join(content_dir, f"{safe_uid}.json")

            if os.path.exists(out_file):
                skipped += 1
                continue

            try:
                await asyncio.sleep(RATE_LIMIT)
                resp = await client.get(f"{SC_API_BASE}/suttas/{uid}/pali")

                if resp.status_code == 404:
                    with open(out_file, "w") as f:
                        json.dump({"uid": uid, "status": "not_found"}, f)
                    no_content += 1
                elif resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 10))
                    print(f"  Rate limited. Waiting {retry_after}s...")
                    await asyncio.sleep(retry_after)
                    continue
                else:
                    resp.raise_for_status()
                    data = resp.json()
                    data["_uid"] = uid
                    with open(out_file, "w") as f:
                        json.dump(data, f, ensure_ascii=False)
                    downloaded += 1

            except Exception as e:
                errors += 1
                if errors <= 10:
                    print(f"  Error {uid}: {e}")

            if (i + 1) % 100 == 0:
                elapsed = time.time() - start
                processed = i - last_idx
                rate = processed / elapsed if elapsed > 0 else 0
                remaining = (len(suttas) - i) / rate / 60 if rate > 0 else 0
                print(f"  Progress: {i + 1}/{len(suttas)} | "
                      f"downloaded={downloaded} skipped={skipped} no_content={no_content} errors={errors} | "
                      f"~{remaining:.0f}min remaining")
                save_checkpoint({"last_content_idx": i})

        save_checkpoint({"last_content_idx": len(suttas) - 1, "content_done": True})

        print(f"\n{'='*50}")
        print(f"SuttaCentral download complete:")
        print(f"  Downloaded: {downloaded}")
        print(f"  Skipped (existing): {skipped}")
        print(f"  No content (404): {no_content}")
        print(f"  Errors: {errors}")
        print(f"  Output: {OUTPUT_DIR}")
        print(f"{'='*50}")


if __name__ == "__main__":
    asyncio.run(main())
