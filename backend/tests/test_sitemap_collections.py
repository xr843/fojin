"""The 13 curated collection series each have their own URL now
(/collections/<id>); the sitemap has to name them or the deep links stay
invisible to crawlers — which was most of the point of adding them.
"""

import json
from pathlib import Path

from app.api.sitemap import STATIC_PAGES

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
_COLLECTIONS_JSON = _FRONTEND / "src" / "content" / "collectionLocales" / "zh.json"


def _curated_collection_ids() -> list[str]:
    data = json.loads(_COLLECTIONS_JSON.read_text(encoding="utf-8"))
    return [c["id"] for c in data["collections"]]


def test_every_curated_collection_is_in_the_sitemap():
    paths = {p for p, _, _ in STATIC_PAGES}
    missing = [
        f"/collections/{cid}"
        for cid in _curated_collection_ids()
        if f"/collections/{cid}" not in paths
    ]
    assert not missing, f"collection deep links missing from sitemap: {missing}"


def test_sitemap_has_no_stale_collection_links():
    curated = set(_curated_collection_ids())
    listed = {
        p.removeprefix("/collections/")
        for p, _, _ in STATIC_PAGES
        if p.startswith("/collections/")
    }
    assert listed <= curated, f"sitemap lists collections that no longer exist: {listed - curated}"


def test_cross_canon_browse_page_is_listed():
    # ~1000 aligned texts, a bigger index than /collections, previously absent.
    assert "/cross-canon" in {p for p, _, _ in STATIC_PAGES}
