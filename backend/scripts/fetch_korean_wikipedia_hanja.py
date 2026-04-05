"""Fallback: Query Korean Wikipedia API for Hanja in infoboxes.

Extracts {{한자|...|漢字}} or '''韓文''' ([[漢字]]) patterns from wikitext.
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request

USER_AGENT = "FoJinBot/1.0 (https://fojin.app)"
INPUT = "data/korean_hangul_names.json"
EXISTING = "data/korean_hanja_map.json"
OUTPUT = "data/korean_hanja_map.json"

# Patterns to extract Chinese characters from Korean Wikipedia wikitext
HANJA_PATTERNS = [
    r"\|\s*한자\s*=\s*([一-龥]{2,15})",
    r"\|\s*hanja\s*=\s*([一-龥]{2,15})",
    r"\{\{llang\|ko-hani\|([一-龥]{2,15})",
    r"\{\{한자\|[^\}]*\|([一-龥]{2,15})",
    # Pattern: '''한글'''(한자, ''romanization'')
    r"'''[가-힣\s]+''?'\s*\(([一-龥]{2,15})[^)]*\)",
    r"\(\s*[一-龥]{0,2}?\s*:\s*([一-龥]{2,15})\s*[,\)]",
]


def extract_hanja(wikitext: str) -> str | None:
    for pat in HANJA_PATTERNS:
        m = re.search(pat, wikitext)
        if m:
            hanja = m.group(1).strip()
            if 2 <= len(hanja) <= 15:
                return hanja
    return None


def fetch_wikipedia(title: str) -> str | None:
    params = urllib.parse.urlencode({
        "action": "parse",
        "page": title,
        "prop": "wikitext",
        "format": "json",
        "formatversion": "2",
        "redirects": "1",
    })
    url = f"https://ko.wikipedia.org/w/api.php?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        parse = data.get("parse", {})
        wikitext = parse.get("wikitext", "")
        if not wikitext:
            return None
        return extract_hanja(wikitext)
    except Exception:
        return None


def main():
    with open(INPUT) as f:
        names = json.load(f)

    results = {}
    if os.path.exists(EXISTING):
        with open(EXISTING) as f:
            results = json.load(f)

    # Only process names that don't have hanja yet
    to_process = [n for n in names if not results.get(n, {}).get("hanja")]
    print(f"Need to resolve via Wikipedia: {len(to_process)}")

    found_new = 0
    for i, name in enumerate(to_process):
        # Try full name first
        hanja = fetch_wikipedia(name)

        # If name is compound "X산 Y사", try just "Y사"
        if not hanja and " " in name:
            parts = name.split()
            for part in reversed(parts):
                if part.endswith(("사", "암", "원", "궁")) and len(part) >= 2:
                    hanja = fetch_wikipedia(part)
                    if hanja:
                        break

        if hanja:
            results[name] = {"hanja": hanja, "source": "wikipedia_ko"}
            found_new += 1
            if found_new % 10 == 0:
                print(f"  [{i+1}/{len(to_process)}] +{found_new}: {name} → {hanja}")
        else:
            results[name] = {"hanja": None, "source": None}

        if i % 50 == 0 and i > 0:
            with open(OUTPUT, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

        time.sleep(1.0)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    total_found = sum(1 for v in results.values() if v.get("hanja"))
    print(f"\nTotal with Hanja: {total_found}/{len(names)}")


if __name__ == "__main__":
    main()
