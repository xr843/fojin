"""Search facets a reader of the canon can use: 藏经 / 语言 / 朝代 / 部类.

Why the facets are derived at query time instead of indexed
-----------------------------------------------------------
Neither index carries a "canon" or "section (部)" field, and the ``category``
field is useless as a 部类 facet — measured on production 2026-10-11, of the
4,130 Chinese texts 2,347 say ``大正藏`` and 1,228 say ``卍新纂續藏經`` (a canon
name, not a section); real section labels (般若部 …) exist on 2 texts.

But both are fully determined by ``cbeta_id``, which both indexes store as a
``keyword``:

* the canon is its prefix — the same rule as ``services/text.canon_from_cbeta_id``
  (T → 大正藏, X → 卍續藏, SC-/VRI- → 巴利, 84K- → 藏文, GRETIL- → 梵文);
* the Taishō numbering *is* the section order (see ``canon_class.py``), so a
  section is a lexicographic ``range`` over zero-padded ids: ``T0220`` ≤ id <
  ``T0262`` is 般若部, and ``T0220a`` … ``T0261c`` fall inside it.

So filtering and counting need no reindex, and the 部类 facet covers every
Taishō text (2,901 on prod) instead of 2. Texts outside the Taishō (卍續藏,
Pali, Tibetan, Sanskrit) simply have no section — the facet says nothing about
them rather than guessing.

``dynasty`` and ``lang`` are plain keyword fields in both indexes. Dynasty is
only filled for Chinese texts (2,760 / 4,130 on prod); for other languages the
facet comes back empty and the UI hides it.

Faceting semantics: OR within a group, AND across groups, and each group's
counts are computed with every *other* group's filter applied but not its own
(so ticking 大正藏 does not zero out 卍續藏's count). That is why, when facets
are requested, the four facet filters move from ``query.bool.filter`` to
``post_filter`` — a filter clause never scores, so the hits, their order and
``total`` are identical either way.
"""

from __future__ import annotations

from typing import Any

FACET_GROUPS = ("canon", "lang", "dynasty", "section")

# canon code → cbeta_id prefixes. Codes match canon_from_cbeta_id where it has
# one; jiaxing / nanchuan are listed so a future import shows up without a code
# change (both are absent from the index today — the bucket is simply empty).
CANONS: dict[str, tuple[str, ...]] = {
    "taisho": ("T",),
    "xuzang": ("X",),
    "jiaxing": ("J",),
    "nanchuan": ("N",),
    "pali": ("SC-", "VRI-"),
    "kangyur": ("84K-",),
    "gretil": ("GRETIL-",),
}

# Taishō sections (部) over Taishō numbers, inclusive, in canon order.
# Boundaries cross-checked 2026-10-11 against the section labels that the
# index's own ``category`` field carries for the few texts that have one
# (續經疏 2185–2245, 續律疏 2246–2248, 續論疏 2249–2294, 經集 446–797 …):
# none falls outside the range given here.
SECTIONS: tuple[tuple[str, int, int], ...] = (
    ("agama", 1, 151),  # 阿含部
    ("jataka", 152, 219),  # 本緣部
    ("prajna", 220, 261),  # 般若部
    ("lotus", 262, 277),  # 法華部
    ("avatamsaka", 278, 309),  # 華嚴部
    ("ratnakuta", 310, 373),  # 寶積部
    ("nirvana", 374, 396),  # 涅槃部
    ("mahasamnipata", 397, 424),  # 大集部
    ("sutra_collection", 425, 847),  # 經集部
    ("esoteric", 848, 1420),  # 密教部
    ("vinaya", 1421, 1504),  # 律部
    ("sutra_treatise", 1505, 1535),  # 釋經論部
    ("abhidharma", 1536, 1563),  # 毘曇部
    ("madhyamaka", 1564, 1578),  # 中觀部
    ("yogacara", 1579, 1627),  # 瑜伽部
    ("treatise_collection", 1628, 1692),  # 論集部
    ("sutra_commentary", 1693, 1803),  # 經疏部
    ("vinaya_commentary", 1804, 1815),  # 律疏部
    ("treatise_commentary", 1816, 1850),  # 論疏部
    ("schools", 1851, 2025),  # 諸宗部
    ("history", 2026, 2120),  # 史傳部
    ("encyclopedia", 2121, 2136),  # 事彙部
    ("non_buddhist", 2137, 2144),  # 外教部
    ("catalogue", 2145, 2184),  # 目錄部
    ("j_sutra_commentary", 2185, 2245),  # 續經疏部
    ("j_vinaya_commentary", 2246, 2248),  # 續律疏部
    ("j_treatise_commentary", 2249, 2295),  # 續論疏部
    ("j_schools", 2296, 2700),  # 續諸宗部
    ("siddham", 2701, 2731),  # 悉曇部
    ("dunhuang", 2732, 2864),  # 古逸部
    ("apocrypha", 2865, 2920),  # 疑似部
)
_SECTION_BY_CODE = {code: (first, last) for code, first, last in SECTIONS}

# Bucket sizes for the two keyword facets. Prod has 16 dynasties and 4 langs.
_DYNASTY_AGG_SIZE = 50
_LANG_AGG_SIZE = 20


def split_multi(value: str | None) -> list[str]:
    """``"a,b"`` → ``["a", "b"]``; blanks dropped, order kept, duplicates removed.

    A single value is the pre-facet query-string shape, so every old caller
    (``?dynasty=唐``, ``?lang=lzh``) is just the one-element case.
    """
    out: list[str] = []
    for part in (value or "").split(","):
        part = part.strip()
        if part and part not in out:
            out.append(part)
    return out


def _keyword_clause(field: str, values: list[str]) -> dict | None:
    if not values:
        return None
    # One value stays a `term` — byte-identical to the body these endpoints
    # sent before multi-select existed.
    if len(values) == 1:
        return {"term": {field: values[0]}}
    return {"terms": {field: values}}


def _canon_query(code: str) -> dict:
    prefixes = CANONS[code]
    if len(prefixes) == 1:
        return {"prefix": {"cbeta_id": prefixes[0]}}
    return {"bool": {"should": [{"prefix": {"cbeta_id": p}} for p in prefixes], "minimum_should_match": 1}}


def _section_query(code: str) -> dict:
    first, last = _SECTION_BY_CODE[code]
    # Zero-padded keyword range: "T0220" ≤ id < "T0262" holds T0220, T0220a … T0261c.
    return {"range": {"cbeta_id": {"gte": f"T{first:04d}", "lt": f"T{last + 1:04d}"}}}


def _any_of(queries: list[dict]) -> dict | None:
    if not queries:
        return None
    if len(queries) == 1:
        return queries[0]
    return {"bool": {"should": queries, "minimum_should_match": 1}}


def facet_clauses(
    *,
    canon: str | None = None,
    lang: str | None = None,
    dynasty: str | None = None,
    section: str | None = None,
) -> dict[str, dict]:
    """One ES filter clause per *active* facet group. Unknown codes are ignored."""
    clauses: dict[str, dict | None] = {
        "canon": _any_of([_canon_query(c) for c in split_multi(canon) if c in CANONS]),
        "lang": _keyword_clause("lang", split_multi(lang)),
        "dynasty": _keyword_clause("dynasty", split_multi(dynasty)),
        "section": _any_of([_section_query(c) for c in split_multi(section) if c in _SECTION_BY_CODE]),
    }
    return {g: c for g, c in clauses.items() if c is not None}


def combine_filters(clauses: list[dict]) -> dict:
    if not clauses:
        return {"match_all": {}}
    if len(clauses) == 1:
        return clauses[0]
    return {"bool": {"filter": clauses}}


def build_facet_aggs(active: dict[str, dict], *, works_field: str | None = None) -> dict:
    """Aggregations for the four groups, each filtered by the *other* groups.

    ``works_field``: count distinct values of this field instead of documents.
    The content index has one document per juan, and its result list is
    collapsed to one row per work — so its facet counts must be works too.
    """

    def sub(bucket: dict) -> dict:
        if works_field:
            bucket["aggs"] = {"works": {"cardinality": {"field": works_field}}}
        return bucket

    def others(group: str) -> dict:
        return combine_filters([c for g, c in active.items() if g != group])

    return {
        "facet_canon": {
            "filter": others("canon"),
            "aggs": {"b": sub({"filters": {"filters": {c: _canon_query(c) for c in CANONS}}})},
        },
        "facet_section": {
            "filter": others("section"),
            "aggs": {"b": sub({"filters": {"filters": {c: _section_query(c) for c, _, _ in SECTIONS}}})},
        },
        "facet_dynasty": {
            "filter": others("dynasty"),
            "aggs": {"b": sub({"terms": {"field": "dynasty", "size": _DYNASTY_AGG_SIZE}})},
        },
        "facet_lang": {
            "filter": others("lang"),
            "aggs": {"b": sub({"terms": {"field": "lang", "size": _LANG_AGG_SIZE}})},
        },
    }


def _count(bucket: dict, works_field: str | None) -> int:
    if works_field:
        return int(bucket.get("works", {}).get("value", 0))
    return int(bucket.get("doc_count", 0))


def parse_facet_aggs(aggregations: dict[str, Any] | None, *, works_field: str | None = None) -> dict:
    """ES aggregations → ``{group: [{"key", "count"}]}``, zero buckets dropped.

    canon / section keep their table order (canon order, Taishō order);
    dynasty / lang come back by count — the client orders dynasties
    chronologically itself.
    """
    aggs = aggregations or {}
    out: dict[str, list[dict[str, Any]]] = {}

    for group, order in (("canon", list(CANONS)), ("section", [c for c, _, _ in SECTIONS])):
        buckets = aggs.get(f"facet_{group}", {}).get("b", {}).get("buckets", {}) or {}
        out[group] = [
            {"key": key, "count": n} for key in order if key in buckets and (n := _count(buckets[key], works_field)) > 0
        ]

    for group in ("dynasty", "lang"):
        buckets = aggs.get(f"facet_{group}", {}).get("b", {}).get("buckets", []) or []
        rows = [{"key": b["key"], "count": _count(b, works_field)} for b in buckets if b.get("key")]
        out[group] = sorted((r for r in rows if r["count"] > 0), key=lambda r: -r["count"])

    return out


# ── SQL twin for the pgvector semantic search ──────────────────────────


def facet_sql(
    *,
    canon: str | None,
    section: str | None,
    start_idx: int,
    column: str = "bt.cbeta_id",
) -> tuple[list[str], list[Any]]:
    """``AND …`` fragments + positional params for canon / section on ``column``.

    Same rules as the ES clauses: canon is a prefix match, section a Taishō
    number range. The number is only cast when the id really is ``T`` + four
    digits (CASE, because Postgres does not promise AND short-circuits).
    """
    fragments: list[str] = []
    params: list[Any] = []
    idx = start_idx

    prefixes = [p for c in split_multi(canon) if c in CANONS for p in CANONS[c]]
    if prefixes:
        ors = []
        for p in prefixes:
            ors.append(f"{column} LIKE ${idx}")
            params.append(p + "%")
            idx += 1
        fragments.append(f"AND ({' OR '.join(ors)})")

    ranges = [_SECTION_BY_CODE[c] for c in split_multi(section) if c in _SECTION_BY_CODE]
    if ranges:
        num = f"(CASE WHEN {column} ~ '^T[0-9]{{4}}' THEN substring({column} from 2 for 4)::int END)"
        ors = []
        for first, last in ranges:
            ors.append(f"{num} BETWEEN ${idx} AND ${idx + 1}")
            params.extend([first, last])
            idx += 2
        fragments.append(f"AND ({' OR '.join(ors)})")

    return fragments, params
