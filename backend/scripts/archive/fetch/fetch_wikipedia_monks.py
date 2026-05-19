#!/usr/bin/env python3
"""Fetch Chinese Buddhist monk data from zh.wikipedia via MediaWiki API."""

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://zh.wikipedia.org/w/api.php"
UA = "FoJinBot/1.0 (https://fojin.app; contact@fojin.app)"
RATE_LIMIT = 1.0

CATEGORIES = [
    # zh.wikipedia uses traditional Chinese for category names
    "Category:漢傳佛教出家眾", "Category:中國佛教出家眾",
    "Category:禪宗人物", "Category:禪僧",
    "Category:淨土宗僧人 (中國)", "Category:天台宗僧人",
    "Category:華嚴宗人物", "Category:中國法相宗僧人",
    "Category:唐朝僧人", "Category:宋朝僧人", "Category:明朝僧人", "Category:清朝僧人",
    "Category:元朝僧人", "Category:隋朝僧人", "Category:南北朝僧人", "Category:晉朝僧人",
]

DYNASTY_KEYWORDS = [
    "唐朝", "宋朝", "明朝", "清朝", "元朝", "隋朝", "南北朝",
    "东晋", "西晋", "東晉", "西晉", "五代十国", "五代十國", "三国", "三國",
    "汉朝", "漢朝", "东汉", "東漢", "西汉", "西漢", "民国", "民國", "晉朝",
]
SCHOOL_KEYWORDS = [
    "禅宗", "禪宗", "净土宗", "淨土宗", "天台宗", "华严宗", "華嚴宗",
    "唯识宗", "唯識宗", "律宗", "密宗", "三论宗", "三論宗",
    "法相宗", "临济宗", "臨濟宗", "曹洞宗", "沩仰宗", "溈仰宗",
    "云门宗", "雲門宗", "法眼宗",
]

_last_req = 0.0


def api_get(params: dict, retries: int = 3) -> dict:
    global _last_req
    elapsed = time.time() - _last_req
    if elapsed < RATE_LIMIT:
        time.sleep(RATE_LIMIT - elapsed)
    params["format"] = "json"
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{API}?{qs}", headers={"User-Agent": UA})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                _last_req = time.time()
                return json.loads(resp.read())
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
            else:
                raise


def get_category_members(category: str, max_depth: int = 2) -> dict[int, str]:
    """Return {page_id: title} for articles in category (recursive)."""
    pages = {}
    queue = [(category, 0)]
    visited = set()
    while queue:
        cat, depth = queue.pop(0)
        if cat in visited:
            continue
        visited.add(cat)
        cmcontinue = None
        while True:
            p = {"action": "query", "list": "categorymembers",
                 "cmtitle": cat, "cmlimit": "500"}
            if cmcontinue:
                p["cmcontinue"] = cmcontinue
            data = api_get(p)
            for m in data.get("query", {}).get("categorymembers", []):
                if m["ns"] == 0:
                    pages[m["pageid"]] = m["title"]
                elif m["ns"] == 14 and depth < max_depth:
                    queue.append((m["title"], depth + 1))
            cmcontinue = data.get("continue", {}).get("cmcontinue")
            if not cmcontinue:
                break
    return pages


def fetch_page_batch(page_ids: list[int]) -> list[dict]:
    """Fetch extracts, pageprops, categories for a batch of pages (max 50)."""
    data = api_get({
        "action": "query", "pageids": "|".join(str(i) for i in page_ids),
        "prop": "extracts|pageprops|categories",
        "exintro": "1", "explaintext": "1", "exlimit": str(len(page_ids)),
        "ppprop": "wikibase_item",
        "cllimit": "max", "clshow": "!hidden",
        "redirects": "1",
    })
    results = []
    for pid_str, page in data.get("query", {}).get("pages", {}).items():
        if int(pid_str) < 0:
            continue
        cats = [c["title"].replace("Category:", "") for c in page.get("categories", [])]
        qid = page.get("pageprops", {}).get("wikibase_item")
        extract = (page.get("extract") or "").strip()
        title = page.get("title", "")

        dynasty = None
        for kw in DYNASTY_KEYWORDS:
            if any(kw in c for c in cats):
                dynasty = kw
                break

        school = None
        for kw in SCHOOL_KEYWORDS:
            if any(kw in c for c in cats):
                school = kw
                break

        results.append({
            "name": title,
            "dynasty": dynasty,
            "school": school,
            "wikidata_qid": qid,
            "extract": extract[:500] if extract else None,
            "source_url": f"https://zh.wikipedia.org/wiki/{urllib.parse.quote(title)}",
            "categories": cats,
        })
    return results


def main():
    out_path = Path(__file__).resolve().parent.parent.parent / "data" / "wikipedia_monks.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Phase 1: enumerate categories
    all_pages: dict[int, str] = {}
    print("=== Enumerating categories ===")
    for cat in CATEGORIES:
        pages = get_category_members(cat)
        print(f"  {cat}: {len(pages)} articles")
        all_pages.update(pages)
    print(f"\nTotal unique articles: {len(all_pages)}")

    # Phase 2: fetch page data in batches of 50
    page_ids = sorted(all_pages.keys())
    monks = []
    print(f"\n=== Fetching page data ({len(page_ids)} pages) ===")
    for i in range(0, len(page_ids), 50):
        batch = page_ids[i:i+50]
        if i % 200 == 0:
            print(f"  [{i}/{len(page_ids)}]")
        try:
            monks.extend(fetch_page_batch(batch))
        except Exception as e:
            print(f"  ERROR at batch {i}: {e}")

    # Stats
    with_dynasty = sum(1 for m in monks if m["dynasty"])
    with_school = sum(1 for m in monks if m["school"])
    with_qid = sum(1 for m in monks if m["wikidata_qid"])
    with_extract = sum(1 for m in monks if m["extract"])

    print(f"\n=== Results ===")
    print(f"Total monks: {len(monks)}")
    print(f"With dynasty: {with_dynasty}")
    print(f"With school: {with_school}")
    print(f"With Wikidata QID: {with_qid}")
    print(f"With extract: {with_extract}")

    print(f"\n=== Sample entries ===")
    for m in monks[:3]:
        print(json.dumps(m, ensure_ascii=False, indent=2))

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(monks, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
