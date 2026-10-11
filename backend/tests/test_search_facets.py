"""Search facets 藏经 / 语言 / 朝代 / 部类 (services/search_facets.py).

The load-bearing guarantee is the first block: a search with no facet filter
must send Elasticsearch exactly the body it sent before facets existed, so the
default ranking and recall cannot have moved. ``snapshots/search_default_bodies.json``
was recorded from master 374aa1a (before this change) for the four reference
queries; with ``facets=true`` the only allowed difference is the added ``aggs``.
"""

import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import search as S
from app.services.canon_class import canon_class
from app.services.search_facets import (
    CANONS,
    SECTIONS,
    build_facet_aggs,
    facet_clauses,
    facet_sql,
    parse_facet_aggs,
    split_multi,
)

SNAPSHOT = json.loads((Path(__file__).parent / "snapshots" / "search_default_bodies.json").read_text("utf-8"))
QUERIES = ["般若", "心经", "阿弥陀", "四圣谛"]
EMPTY = {"hits": {"total": {"value": 0}, "hits": []}, "aggregations": {}}


def _es():
    es = MagicMock()
    es.search = AsyncMock(return_value=copy.deepcopy(EMPTY))
    return es


def _bodies(es) -> list[dict]:
    return [
        c.kwargs["body"]
        for c in es.search.call_args_list
        if c.kwargs.get("index") in ("buddhist_texts", "text_contents")
    ]


async def _capture(q: str, **kw) -> list[dict]:
    """Same call sequence the snapshot was recorded with."""
    es = _es()
    await S.search_texts(es, q, 1, 20, **kw)
    await S.search_texts(es, q, 1, 10, **kw)
    await S.search_content(es, q, 1, 20, **kw)
    await S.search_content(es, q, 1, 5, **kw)
    await S.search_cross_language(es, q, 1, 20)
    return _bodies(es)


# ── 1. default search is untouched ───────────────────────────────────────


@pytest.mark.parametrize("q", QUERIES)
async def test_default_bodies_identical_to_pre_facet_snapshot(q):
    assert await _capture(q) == SNAPSHOT[q]


@pytest.mark.parametrize("q", QUERIES)
async def test_facets_on_without_filter_only_adds_aggs(q):
    """facets=true, nothing ticked: query/sort/highlight/from/size are the
    snapshot's — the hits cannot differ; only aggregations are added."""
    got = await _capture(q, facets=True)
    want = SNAPSHOT[q]
    assert len(got) == len(want)
    for g, w in zip(got, want, strict=True):
        assert "post_filter" not in g
        g_no_facets = {k: v for k, v in g.items() if k != "aggs"}
        w_no_aggs = {k: v for k, v in w.items() if k != "aggs"}
        assert g_no_facets == w_no_aggs
        # The content index's own totals aggs survive unchanged next to the facets.
        for name, agg in (w.get("aggs") or {}).items():
            assert g["aggs"][name] == agg


@pytest.mark.parametrize("q", QUERIES)
async def test_semantic_sql_identical_to_pre_facet_snapshot(q):
    db, conn = MagicMock(), MagicMock()
    res = MagicMock()
    res.fetchall = MagicMock(return_value=[])
    conn.exec_driver_sql = AsyncMock(return_value=res)
    db.connection = AsyncMock(return_value=conn)
    with patch.object(S, "generate_embedding", AsyncMock(return_value=[0.1, 0.2])):
        await S.search_semantic(db, q, 20)
    sql, params = conn.exec_driver_sql.call_args.args
    assert {"sql": sql, "params": list(params)} == SNAPSHOT["_semantic"][q]


async def test_single_old_style_filters_keep_their_old_clause_shape():
    """?dynasty=唐&lang=lzh from an old client: same `term` clauses, same order."""
    es = _es()
    await S.search_texts(es, "般若", dynasty="唐", category="大正藏", lang="lzh", sources="cbeta")
    assert _bodies(es)[0]["query"]["bool"]["filter"] == [
        {"term": {"dynasty": "唐"}},
        {"term": {"category": "大正藏"}},
        {"term": {"lang": "lzh"}},
        {"term": {"source_code": "cbeta"}},
    ]


# ── 2. filters ───────────────────────────────────────────────────────────


async def test_facet_filters_go_to_bool_filter_without_facets():
    es = _es()
    await S.search_texts(es, "般若", canon="taisho,xuzang", section="prajna", lang="lzh,pi")
    body = _bodies(es)[0]
    assert "post_filter" not in body
    assert body["query"]["bool"]["filter"] == [
        {"terms": {"lang": ["lzh", "pi"]}},
        {
            "bool": {
                "should": [{"prefix": {"cbeta_id": "T"}}, {"prefix": {"cbeta_id": "X"}}],
                "minimum_should_match": 1,
            }
        },
        {"range": {"cbeta_id": {"gte": "T0220", "lt": "T0262"}}},
    ]


async def test_facet_filters_move_to_post_filter_with_facets():
    es = _es()
    await S.search_texts(es, "般若", canon="taisho", dynasty="唐", sources="cbeta", facets=True)
    body = _bodies(es)[0]
    # Non-facet filters stay in the query; facet groups move out of it.
    assert body["query"]["bool"]["filter"] == [{"term": {"source_code": "cbeta"}}]
    assert body["post_filter"] == {"bool": {"filter": [{"prefix": {"cbeta_id": "T"}}, {"term": {"dynasty": "唐"}}]}}
    # Each group's counts apply every *other* group's filter, never its own.
    assert body["aggs"]["facet_canon"]["filter"] == {"term": {"dynasty": "唐"}}
    assert body["aggs"]["facet_dynasty"]["filter"] == {"prefix": {"cbeta_id": "T"}}
    assert body["aggs"]["facet_lang"]["filter"] == body["post_filter"]


async def test_unknown_codes_are_ignored_not_errors():
    assert facet_clauses(canon="nope", section="also-nope") == {}
    assert split_multi(" a, ,b,a ") == ["a", "b"]


async def test_cross_language_takes_canon_section_dynasty_but_not_lang():
    es = _es()
    await S.search_cross_language(es, "般若", dynasty="唐,宋", canon="taisho", section="prajna")
    assert _bodies(es)[0]["query"]["bool"]["filter"] == [
        {"terms": {"dynasty": ["唐", "宋"]}},
        {"prefix": {"cbeta_id": "T"}},
        {"range": {"cbeta_id": {"gte": "T0220", "lt": "T0262"}}},
    ]


# ── 3. section ranges ────────────────────────────────────────────────────


def _in_es_range(cbeta_id: str, clause: dict) -> bool:
    """ES keyword range = byte-wise string comparison, like Python's."""
    r = clause["range"]["cbeta_id"]
    return r["gte"] <= cbeta_id < r["lt"]


def test_sections_tile_the_taisho_without_gap_or_overlap():
    expected_first = 1
    for _code, first, last in SECTIONS:
        assert first == expected_first
        assert last >= first
        expected_first = last + 1
    assert expected_first - 1 == 2920  # T2920 is the last Taishō number


@pytest.mark.parametrize(
    ("cbeta_id", "section"),
    [
        ("T0001", "agama"),
        ("T0151", "agama"),
        ("T0220", "prajna"),
        ("T0220a", "prajna"),  # 大般若經 is split T0220a…T0220o
        ("T0251", "prajna"),  # 心經
        ("T0261", "prajna"),
        ("T0262", "lotus"),
        ("T0278", "avatamsaka"),
        ("T0366", "ratnakuta"),  # 阿彌陀經
        ("T1421", "vinaya"),
        ("T1564", "madhyamaka"),
        ("T1585", "yogacara"),  # 成唯識論
        ("T2008", "schools"),  # 六祖壇經
        ("T2246", "j_vinaya_commentary"),
        ("T2731", "siddham"),
        ("T2920", "apocrypha"),
    ],
)
def test_section_range_puts_id_in_exactly_one_section(cbeta_id, section):
    hits = [code for code, _, _ in SECTIONS if _in_es_range(cbeta_id, facet_clauses(section=code)["section"])]
    assert hits == [section]


@pytest.mark.parametrize("cbeta_id", ["X0001", "SC-dn1", "84K-toh1", "GRETIL-bsu056_u", "T"])
def test_non_taisho_ids_have_no_section(cbeta_id):
    assert not any(_in_es_range(cbeta_id, facet_clauses(section=code)["section"]) for code, _, _ in SECTIONS)


def test_sections_agree_with_canon_class():
    """The verify page's sūtra/vinaya/treatise split and these sections are the same Taishō order."""
    by_class = {"sutra": (1, 1420), "vinaya": (1421, 1504), "treatise": (1505, 1692)}
    for code, first, last in SECTIONS:
        for n in (first, last):
            cls = canon_class(f"T{n:04d}")
            if cls in by_class:
                lo, hi = by_class[cls]
                assert lo <= n <= hi, code


def test_canon_codes_cover_the_live_prefixes():
    # Prefixes seen on prod 2026-10-11 (all 10,531 texts).
    for cid, code in [
        ("T0001", "taisho"),
        ("X0001", "xuzang"),
        ("SC-dn1", "pali"),
        ("VRI-dn-patika", "pali"),
        ("84K-toh1", "kangyur"),
        ("GRETIL-bsu056_u", "gretil"),
    ]:
        assert any(cid.startswith(p) for p in CANONS[code])


# ── 4. parsing ───────────────────────────────────────────────────────────


def test_parse_facet_aggs_orders_and_drops_zero():
    aggs = {
        "facet_canon": {
            "b": {"buckets": {"taisho": {"doc_count": 5}, "xuzang": {"doc_count": 0}, "pali": {"doc_count": 2}}}
        },
        "facet_section": {"b": {"buckets": {"prajna": {"doc_count": 3}, "agama": {"doc_count": 1}}}},
        "facet_dynasty": {"b": {"buckets": [{"key": "宋", "doc_count": 1}, {"key": "唐", "doc_count": 4}]}},
        "facet_lang": {"b": {"buckets": [{"key": "lzh", "doc_count": 7}]}},
    }
    assert parse_facet_aggs(aggs) == {
        "canon": [{"key": "taisho", "count": 5}, {"key": "pali", "count": 2}],
        "section": [{"key": "agama", "count": 1}, {"key": "prajna", "count": 3}],  # Taishō order
        "dynasty": [{"key": "唐", "count": 4}, {"key": "宋", "count": 1}],
        "lang": [{"key": "lzh", "count": 7}],
    }


def test_parse_facet_aggs_counts_works_for_content_index():
    aggs = build_facet_aggs({}, works_field="text_id")
    assert aggs["facet_lang"]["aggs"]["b"]["aggs"] == {"works": {"cardinality": {"field": "text_id"}}}
    parsed = parse_facet_aggs(
        {"facet_lang": {"b": {"buckets": [{"key": "lzh", "doc_count": 90, "works": {"value": 12}}]}}},
        works_field="text_id",
    )
    assert parsed["lang"] == [{"key": "lzh", "count": 12}]


def test_parse_facet_aggs_tolerates_missing_aggregations():
    assert parse_facet_aggs(None) == {"canon": [], "section": [], "dynasty": [], "lang": []}


async def test_content_totals_respect_post_filter():
    """Aggregations ignore post_filter — the works/juans totals must not."""
    es = _es()
    es.search.return_value = {
        "hits": {"total": {"value": 0}, "hits": []},
        "aggregations": {"totals": {"total_works": {"value": 3}, "total_juans": {"value": 9}}},
    }
    out = await S.search_content(es, "般若", 1, 20, canon="taisho", facets=True)
    body = _bodies(es)[0]
    assert body["post_filter"] == {"prefix": {"cbeta_id": "T"}}
    assert body["aggs"]["totals"]["filter"] == body["post_filter"]
    assert (out["total"], out["total_juans"]) == (3, 9)
    assert set(out["facets"]) == {"canon", "section", "dynasty", "lang"}


# ── 5. semantic SQL ──────────────────────────────────────────────────────


def test_facet_sql_fragments():
    frags, params = facet_sql(canon="taisho,pali", section="prajna", start_idx=5)
    assert frags == [
        "AND (bt.cbeta_id LIKE $5 OR bt.cbeta_id LIKE $6 OR bt.cbeta_id LIKE $7)",
        "AND ((CASE WHEN bt.cbeta_id ~ '^T[0-9]{4}' THEN substring(bt.cbeta_id from 2 for 4)::int END)"
        " BETWEEN $8 AND $9)",
    ]
    assert params == ["T%", "SC-%", "VRI-%", 220, 261]


async def test_semantic_multi_select_sql():
    db, conn = MagicMock(), MagicMock()
    res = MagicMock()
    res.fetchall = MagicMock(return_value=[])
    conn.exec_driver_sql = AsyncMock(return_value=res)
    db.connection = AsyncMock(return_value=conn)
    with patch.object(S, "generate_embedding", AsyncMock(return_value=[0.1])):
        await S.search_semantic(db, "般若", 20, dynasty="唐,宋", lang="lzh", canon="taisho")
    sql, params = conn.exec_driver_sql.call_args.args
    assert "AND bt.dynasty IN ($4, $5)" in sql
    assert "AND bt.lang = $6" in sql
    assert "AND (bt.cbeta_id LIKE $7)" in sql
    assert list(params)[3:] == ["唐", "宋", "lzh", "T%"]


# ── 6. HTTP layer ────────────────────────────────────────────────────────


async def test_api_search_old_call_unchanged_and_facets_null(client, mock_es):
    resp = await client.get("/api/search", params={"q": "般若", "dynasty": "唐"})
    assert resp.status_code == 200
    assert resp.json()["facets"] is None
    body = mock_es.search.call_args_list[0].kwargs["body"]
    assert "aggs" not in body and "post_filter" not in body


async def test_api_search_returns_facets(client, mock_es):
    mock_es.search.return_value = {
        **mock_es.search.return_value,
        "aggregations": {"facet_canon": {"b": {"buckets": {"taisho": {"doc_count": 2}}}}},
    }
    resp = await client.get("/api/search", params={"q": "般若", "facets": "true", "canon": "taisho"})
    assert resp.status_code == 200
    assert resp.json()["facets"]["canon"] == [{"key": "taisho", "count": 2}]
    body = mock_es.search.call_args_list[0].kwargs["body"]
    assert body["post_filter"] == {"prefix": {"cbeta_id": "T"}}


async def test_unified_passes_facets_through():
    from app.api import search_unified as U

    fake_catalog = S.SearchResponse(total=0, page=1, size=10, results=[], facets={"lang": [{"key": "lzh", "count": 1}]})
    texts = AsyncMock(return_value=fake_catalog)
    content = AsyncMock(return_value={"total": 0, "results": []})
    semantic = AsyncMock(return_value=S.SemanticSearchResponse(total=0, results=[]))
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=MagicMock())
    session_cm.__aexit__ = AsyncMock(return_value=False)
    request = MagicMock()
    request.app.state = MagicMock(spec=[])
    with (
        patch.object(U, "search_texts", texts),
        patch.object(U, "search_content", content),
        patch.object(U, "search_semantic", semantic),
        patch.object(U, "_dict_top_hits", AsyncMock(return_value=[])),
        patch.object(U, "get_es", MagicMock()),
        patch.object(U, "async_session", MagicMock(return_value=session_cm)),
    ):
        out = await U.search_unified(
            request, q="般若", sources=None, lang="lzh", dynasty="唐", canon="taisho", section="prajna", facets=True
        )
        old = await U.search_unified(
            request, q="般若", sources=None, lang=None, dynasty=None, canon=None, section=None, facets=False
        )
    assert out["facets"] == {"lang": [{"key": "lzh", "count": 1}]}
    assert "facets" not in old
    kw = texts.call_args_list[0].kwargs
    assert (kw["canon"], kw["section"], kw["dynasty"], kw["facets"]) == ("taisho", "prajna", "唐", True)
    assert content.call_args_list[0].kwargs["canon"] == "taisho"
    assert semantic.call_args_list[0].kwargs["section"] == "prajna"
