"""
Download 84000 TEI XML files from their GitHub data-tei repository.

The 84000/data-tei repo contains published translations in TEI XML format.
This script downloads them directly via GitHub API.

Saves XML files to data/84000_download/
"""

import asyncio
import os
import sys
import time

import httpx

GITHUB_API = "https://api.github.com"
REPO = "84000/data-tei"
TRANSLATIONS_PATH = "translations/kangyur/translations"
TENGYUR_PATH = "translations/tengyur/translations"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/main"

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "84000_download")
RATE_LIMIT = 0.3  # GitHub API is generous


async def list_xml_files(client: httpx.AsyncClient, path: str) -> list[dict]:
    """List XML files in a GitHub repo directory."""
    files = []
    url = f"{GITHUB_API}/repos/{REPO}/contents/{path}"

    try:
        resp = await client.get(url)
        if resp.status_code != 200:
            print(f"  Could not list {path}: HTTP {resp.status_code}")
            return files

        data = resp.json()
        if isinstance(data, list):
            for item in data:
                if item.get("name", "").endswith(".xml"):
                    files.append({
                        "name": item["name"],
                        "download_url": item.get("download_url") or f"{RAW_BASE}/{path}/{item['name']}",
                        "size": item.get("size", 0),
                    })
    except Exception as e:
        print(f"  Error listing {path}: {e}")

    return files


async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        # Discover files
        print("[1/2] Discovering 84000 translation files on GitHub...")
        kangyur_files = await list_xml_files(client, TRANSLATIONS_PATH)
        print(f"  Kangyur: {len(kangyur_files)} files")

        await asyncio.sleep(RATE_LIMIT)
        tengyur_files = await list_xml_files(client, TENGYUR_PATH)
        print(f"  Tengyur: {len(tengyur_files)} files")

        all_files = kangyur_files + tengyur_files
        print(f"  Total: {len(all_files)} XML files to download")

        if not all_files:
            print("No files found!")
            return

        # Download
        print(f"\n[2/2] Downloading XML files...")
        downloaded = 0
        skipped = 0
        errors = 0
        total_size = 0
        start = time.time()

        for i, info in enumerate(all_files):
            out_file = os.path.join(OUTPUT_DIR, info["name"])

            if os.path.exists(out_file):
                skipped += 1
                continue

            try:
                await asyncio.sleep(RATE_LIMIT)
                resp = await client.get(info["download_url"])
                resp.raise_for_status()

                content = resp.text
                if content.strip().startswith("<?xml") or content.strip().startswith("<"):
                    with open(out_file, "w", encoding="utf-8") as f:
                        f.write(content)
                    downloaded += 1
                    total_size += len(content)
                else:
                    errors += 1
                    print(f"  Not XML: {info['name']}")

            except Exception as e:
                errors += 1
                if errors <= 10:
                    print(f"  Error {info['name']}: {e}")

            if (i + 1) % 20 == 0:
                elapsed = time.time() - start
                print(f"  Progress: {i + 1}/{len(all_files)} | "
                      f"downloaded={downloaded} skipped={skipped} errors={errors} | "
                      f"size={total_size/1024/1024:.1f}MB | elapsed={elapsed:.0f}s")

        elapsed = time.time() - start
        print(f"\n{'='*50}")
        print(f"84000 download complete:")
        print(f"  Downloaded: {downloaded}")
        print(f"  Skipped (existing): {skipped}")
        print(f"  Errors: {errors}")
        print(f"  Total size: {total_size/1024/1024:.1f}MB")
        print(f"  Elapsed: {elapsed:.0f}s")
        print(f"  Output: {OUTPUT_DIR}")
        print(f"{'='*50}")


if __name__ == "__main__":
    asyncio.run(main())
