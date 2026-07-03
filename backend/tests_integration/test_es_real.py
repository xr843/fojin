"""Integration tests against a real Elasticsearch (8.13.4 + analysis-icu).

The mocked unit suite (tests/) patches the ES client entirely, so it can
never catch client/server wire mismatches, missing plugins, or query DSL
the real server rejects. These tests close that blind spot by exercising
the actual client handshake, the real index mappings/analyzers from
app.core.elasticsearch, and the real service-layer query paths from
app.services.search that the API layer (app/api/search.py) calls.
"""

import elasticsearch
import pytest

from app.core.elasticsearch import get_es
from app.schemas.text import SearchResponse
from app.services.search import (
    get_aggregations,
    get_suggestions,
    search_content,
    search_texts,
)
from tests_integration.conftest import TEST_CONTENT_INDEX, TEST_INDEX

# --- Seed data ---------------------------------------------------------------
# Titles are stored in Traditional Chinese, exactly as CBETA data is in prod.
# Queries below use Simplified forms to prove the icu_transform
# (Traditional-Simplified) filter is doing real work.

TEXT_DOCS = [
    {
        "id": 1,
        "taisho_id": "T0235",
        "cbeta_id": "T0235",
        "title_zh": "金剛般若波羅蜜經",
        "title_en": "The Diamond Perfection of Wisdom Sutra",
        "translator": "姚秦 鳩摩羅什",
        "dynasty": "姚秦",
        "category": "般若部",
        "fascicle_count": 1,
        "lang": "lzh",
        "source_code": "cbeta",
        "has_content": True,
    },
    {
        "id": 2,
        "taisho_id": "T0251",
        "cbeta_id": "T0251",
        "title_zh": "般若波羅蜜多心經",
        "title_en": "Heart Sutra",
        "translator": "唐 玄奘",
        "dynasty": "唐",
        "category": "般若部",
        "fascicle_count": 1,
        "lang": "lzh",
        "source_code": "cbeta",
        "has_content": True,
    },
    {
        "id": 3,
        "taisho_id": "T0262",
        "cbeta_id": "T0262",
        "title_zh": "妙法蓮華經",
        "title_en": "The Lotus Sutra",
        "translator": "後秦 鳩摩羅什",
        "dynasty": "後秦",
        "category": "法華部",
        "fascicle_count": 7,
        "lang": "lzh",
        "source_code": "cbeta",
        "has_content": False,
    },
]

CONTENT_DOCS = [
    {
        "text_id": 1,
        "cbeta_id": "T0235",
        "title_zh": "金剛般若波羅蜜經",
        "translator": "鳩摩羅什",
        "dynasty": "姚秦",
        "juan_num": 1,
        "content": "如是我聞：一時，佛在舍衛國祇樹給孤獨園，與大比丘眾千二百五十人俱。",
        "char_count": 33,
        "lang": "lzh",
        "source_code": "cbeta",
    },
    {
        "text_id": 1,
        "cbeta_id": "T0235",
        "title_zh": "金剛般若波羅蜜經",
        "translator": "鳩摩羅什",
        "dynasty": "姚秦",
        "juan_num": 2,
        "content": "如是我聞：須菩提！於意云何？可以身相見如來不？",
        "char_count": 23,
        "lang": "lzh",
        "source_code": "cbeta",
    },
    {
        "text_id": 2,
        "cbeta_id": "T0251",
        "title_zh": "般若波羅蜜多心經",
        "translator": "玄奘",
        "dynasty": "唐",
        "juan_num": 1,
        "content": "觀自在菩薩，行深般若波羅蜜多時，照見五蘊皆空，度一切苦厄。",
        "char_count": 28,
        "lang": "lzh",
        "source_code": "cbeta",
    },
]


@pytest.fixture
async def seeded_indices(search_indices):
    es = search_indices
    for doc in TEXT_DOCS:
        await es.index(index=TEST_INDEX, id=str(doc["id"]), document=doc)
    for i, doc in enumerate(CONTENT_DOCS):
        await es.index(index=TEST_CONTENT_INDEX, id=str(i + 1), document=doc)
    await es.indices.refresh(index=[TEST_INDEX, TEST_CONTENT_INDEX])
    return es


# --- Handshake / environment sanity ------------------------------------------


async def test_client_server_handshake(es):
    """info() must succeed and client/server majors must agree.

    This is the test that would have failed loudly on the dependabot
    elasticsearch 8.17 -> 9.4 bump instead of sailing through mocked CI.
    """
    info = await es.info()
    server_version = info["version"]["number"]
    server_major = int(server_version.split(".")[0])
    client_major = int(elasticsearch.__versionstr__.split(".")[0])
    assert client_major == server_major, (
        f"elasticsearch-py {elasticsearch.__versionstr__} vs server "
        f"{server_version}: major version mismatch — bumping the client "
        f"past the server major breaks the wire protocol in production."
    )
    # init_es() must have wired the module-level client the app uses.
    assert get_es() is es


async def test_analysis_icu_plugin_installed(es):
    """Prod images are built from elasticsearch/Dockerfile which installs
    analysis-icu; the app's analyzers (icu_transform) hard-depend on it."""
    plugins = await es.cat.plugins(format="json")
    components = {p["component"] for p in plugins}
    assert "analysis-icu" in components, (
        f"analysis-icu plugin missing (found: {sorted(components)}); "
        "index creation and all CJK search would fail in production."
    )


# --- Index creation / mappings / analyzers ------------------------------------


async def test_index_mappings_and_settings(search_indices):
    """INDEX_SETTINGS / CONTENT_INDEX_SETTINGS are accepted by the real
    server and persist the analyzer wiring we expect."""
    es = search_indices

    mapping = await es.indices.get_mapping(index=TEST_INDEX)
    props = mapping[TEST_INDEX]["mappings"]["properties"]
    assert props["title_zh"]["analyzer"] == "cjk_bigram"
    assert props["title_zh"]["fields"]["raw"]["type"] == "keyword"
    assert props["taisho_id"]["type"] == "keyword"
    assert props["has_content"]["type"] == "boolean"

    cmapping = await es.indices.get_mapping(index=TEST_CONTENT_INDEX)
    cprops = cmapping[TEST_CONTENT_INDEX]["mappings"]["properties"]
    assert cprops["content"]["analyzer"] == "cjk_content"
    assert cprops["content"]["term_vector"] == "with_positions_offsets"

    idx_settings = await es.indices.get_settings(index=TEST_INDEX)
    analysis = idx_settings[TEST_INDEX]["settings"]["index"]["analysis"]
    assert analysis["filter"]["t2s"]["type"] == "icu_transform"
    assert analysis["filter"]["t2s"]["id"] == "Traditional-Simplified"


async def test_icu_transform_analyzes_traditional_to_simplified(search_indices):
    """The custom analyzers must actually run the ICU Traditional->Simplified
    transform and CJK bigramming on the real server."""
    es = search_indices

    resp = await es.indices.analyze(
        index=TEST_INDEX, body={"analyzer": "cjk_bigram", "text": "金剛般若"}
    )
    tokens = [t["token"] for t in resp["tokens"]]
    # Traditional 金剛般若 -> simplified 金刚般若 -> CJK bigrams
    assert tokens == ["金刚", "刚般", "般若"]

    resp = await es.indices.analyze(
        index=TEST_CONTENT_INDEX, body={"analyzer": "cjk_content", "text": "羅漢"}
    )
    tokens = [t["token"] for t in resp["tokens"]]
    assert tokens == ["罗汉"]


# --- Real service-layer search paths (what app/api/search.py calls) -----------


async def test_search_texts_simplified_query_hits_traditional_title(seeded_indices):
    """A Simplified-Chinese abbreviation ("金刚经") must find the
    Traditional-titled Diamond Sutra via t2s + the abbreviation boost."""
    es = seeded_indices
    resp = await search_texts(es, "金刚经")
    assert isinstance(resp, SearchResponse)
    assert resp.total >= 1
    assert resp.results[0].cbeta_id == "T0235"
    assert resp.results[0].title_zh == "金剛般若波羅蜜經"


async def test_search_texts_english_title(seeded_indices):
    es = seeded_indices
    resp = await search_texts(es, "Diamond")
    assert resp.total >= 1
    assert resp.results[0].cbeta_id == "T0235"
    assert resp.results[0].highlight, "expected a real highlight from the server"


async def test_search_texts_term_filters(seeded_indices):
    es = seeded_indices
    resp = await search_texts(es, "", dynasty="唐")
    assert resp.total == 1
    assert resp.results[0].cbeta_id == "T0251"

    resp = await search_texts(es, "", category="般若部")
    assert {r.cbeta_id for r in resp.results} == {"T0235", "T0251"}


async def test_get_aggregations(seeded_indices):
    es = seeded_indices
    aggs = await get_aggregations(es)
    assert set(aggs["dynasties"]) == {"姚秦", "唐", "後秦"}
    assert set(aggs["categories"]) == {"般若部", "法華部"}
    assert aggs["languages"] == ["lzh"]
    assert aggs["sources"] == ["cbeta"]


async def test_get_suggestions_cjk_prefix(seeded_indices):
    es = seeded_indices
    suggestions = await get_suggestions(es, "般若")
    # get_suggestions swallows server errors and returns [] — a non-empty
    # result proves the match_phrase_prefix query is valid on the real server.
    assert suggestions
    assert all("般若" in s for s in suggestions)


async def test_search_content_collapses_by_work(seeded_indices):
    """Simplified query "如是我闻" must match Traditional content 如是我聞,
    collapse the two matching juans of T0235 into one work-level result,
    and produce real server-side highlights."""
    es = seeded_indices
    resp = await search_content(es, "如是我闻")
    assert resp["total"] == 1  # one unique work (cardinality agg)
    assert resp["total_juans"] == 2  # both juans of T0235 matched
    hit = resp["results"][0]
    assert hit["text_id"] == 1
    assert hit["cbeta_id"] == "T0235"
    assert hit["matched_juan_count"] == 2
    assert hit["highlight"] and "<em>" in hit["highlight"][0]
    assert {j["juan_num"] for j in hit["matched_juans"]} == {1, 2}


@pytest.mark.xfail(
    reason=(
        "sort='title' sorts on title_zh.keyword (and sort='dynasty' on "
        "dynasty.keyword) but the mapping defines the keyword subfield as "
        "title_zh.raw and dynasty as a plain keyword field — the real server "
        "rejects the sort. The mocked unit suite can never see this; kept as "
        "xfail documentation until the mapping/sort mismatch is fixed."
    ),
    strict=False,
)
async def test_search_texts_title_sort(seeded_indices):
    es = seeded_indices
    resp = await search_texts(es, "般若", sort="title")
    assert resp.total >= 1
