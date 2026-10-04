"""「全藏出处」短语模式：/search/content?phrase=true。

cjk_content 是二元组分词，标点两侧不产生跨标点的二元组，所以带标点的整句
做 match_phrase 必然落空（生产实测「一切有為法如夢幻泡影」整句短语 5 部、
连《金剛經》本身都不在）——必须按标点切小句、逐句短语匹配且全部命中。
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.search import PHRASE_MAX_CLAUSES, _phrase_clauses, search_content


def _phrases(clauses: list[dict]) -> list[str]:
    return [c["match_phrase"]["content"]["query"] for c in clauses]


def test_splits_at_punctuation_into_phrase_clauses() -> None:
    assert _phrases(_phrase_clauses("一切有為法，如夢幻泡影")) == ["一切有為法", "如夢幻泡影"]
    assert _phrases(_phrase_clauses("舍衛大城乞食。於其城")) == ["舍衛大城乞食", "於其城"]


def test_whitespace_also_separates_clauses() -> None:
    # 前端把标点规整成空格后传来
    assert _phrases(_phrase_clauses("色即是空 空即是色")) == ["色即是空", "空即是色"]


def test_single_char_clauses_are_dropped() -> None:
    # 单字句在全藏里处处命中，只会把结果冲成噪音
    assert _phrases(_phrase_clauses("佛言：善哉，善哉！須菩提")) == ["佛言", "善哉", "善哉", "須菩提"]
    assert _phrase_clauses("空。") == []


def test_clause_count_is_capped() -> None:
    q = "，".join(["如是我聞"] * (PHRASE_MAX_CLAUSES + 5))
    assert len(_phrase_clauses(q)) == PHRASE_MAX_CLAUSES


def test_clauses_are_match_phrase_with_content_analyzer() -> None:
    (clause,) = _phrase_clauses("應無所住而生其心")
    assert clause == {"match_phrase": {"content": {"query": "應無所住而生其心", "analyzer": "cjk_content"}}}


def _fake_es() -> AsyncMock:
    es = AsyncMock()
    es.search.return_value = {"hits": {"hits": []}, "aggregations": {}}
    return es


@pytest.mark.asyncio
async def test_phrase_mode_sends_bool_must_of_all_clauses() -> None:
    es = _fake_es()
    await search_content(es, "一切有為法，如夢幻泡影", size=10, phrase=True)
    query = es.search.await_args.kwargs["body"]["query"]
    assert _phrases(query["bool"]["must"]) == ["一切有為法", "如夢幻泡影"]
    assert "should" not in query["bool"]


@pytest.mark.asyncio
async def test_phrase_mode_keeps_lang_filter() -> None:
    es = _fake_es()
    await search_content(es, "如是我聞", lang="lzh", phrase=True)
    query = es.search.await_args.kwargs["body"]["query"]
    assert query["bool"]["filter"] == [{"term": {"lang": "lzh"}}]
    assert _phrases(query["bool"]["must"][0]["bool"]["must"]) == ["如是我聞"]


@pytest.mark.asyncio
async def test_phrase_mode_with_no_usable_clause_skips_es() -> None:
    es = _fake_es()
    out = await search_content(es, "空。", phrase=True)
    assert out["total"] == 0 and out["results"] == []
    es.search.assert_not_called()


@pytest.mark.asyncio
async def test_default_mode_is_unchanged_plain_match() -> None:
    es = _fake_es()
    await search_content(es, "應無所住而生其心")
    query = es.search.await_args.kwargs["body"]["query"]
    assert query == {"match": {"content": {"query": "應無所住而生其心", "analyzer": "cjk_content"}}}
