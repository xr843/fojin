"""「全藏出处」短语模式：/search/content?phrase=true。

cjk_content 是二元组分词，标点两侧不产生跨标点的二元组，所以带标点的整句
做 match_phrase 必然落空（生产实测「一切有為法如夢幻泡影」整句短语 5 部、
连《金剛經》本身都不在）——必须按标点切小句。

CBETA 原文每 17–20 字还有一个硬换行，换行处同样不生成二元组；阅读器把行合并后
显示，划词选区里没有换行，所以逐句 match_phrase 也会落空（生产 77 段随机经文，
本卷自己只找回 26%）。现在是逐句二元组词袋粗筛 + 逐字核对。
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.search import (
    PHRASE_CANDIDATE_WORKS,
    PHRASE_CANON_WORKS,
    PHRASE_MAX_CLAUSES,
    _phrase_clause_texts,
    _phrase_clauses,
    search_content,
)


def test_splits_at_punctuation_into_clauses() -> None:
    assert _phrase_clause_texts("一切有為法，如夢幻泡影") == ["一切有為法", "如夢幻泡影"]
    assert _phrase_clause_texts("舍衛大城乞食。於其城") == ["舍衛大城乞食", "於其城"]


def test_whitespace_also_separates_clauses() -> None:
    # 前端把标点规整成空格后传来
    assert _phrase_clause_texts("色即是空 空即是色") == ["色即是空", "空即是色"]


def test_single_char_clauses_are_dropped() -> None:
    # 单字句在全藏里处处命中，只会把结果冲成噪音
    assert _phrase_clause_texts("佛言：善哉，善哉！須菩提") == ["佛言", "善哉", "善哉", "須菩提"]
    assert _phrase_clauses("空。") == []


def test_clause_count_is_capped() -> None:
    q = "，".join(["如是我聞"] * (PHRASE_MAX_CLAUSES + 5))
    assert len(_phrase_clauses(q)) == PHRASE_MAX_CLAUSES


def test_clause_may_miss_one_bigram_per_hard_wrap() -> None:
    # 8 字 7 个二元组：最多跨一处换行，允许丢 1 个
    (clause,) = _phrase_clauses("應無所住而生其心")
    assert clause == {
        "match": {"content": {"query": "應無所住而生其心", "analyzer": "cjk_content", "minimum_should_match": "-1"}}
    }
    # 40 字可能跨两处换行
    (long_clause,) = _phrase_clauses("觀" * 40)
    assert long_clause["match"]["content"]["minimum_should_match"] == "-3"


def test_two_char_clause_stays_a_phrase() -> None:
    # 只有一个二元组，「丢一个」等于不设条件
    assert _phrase_clauses("佛言") == [{"match_phrase": {"content": {"query": "佛言", "analyzer": "cjk_content"}}}]


def _work(text_id: int, juans: list[int], title: str = "") -> dict:
    return {
        "_source": {"text_id": text_id, "title_zh": title or f"t{text_id}", "juan_num": juans[0]},
        "_score": 1.0,
        "highlight": {"content": [f"top-{text_id}"]},
        "inner_hits": {
            "matched_juans": {
                "hits": {
                    "total": {"value": len(juans)},
                    "hits": [
                        {"_source": {"juan_num": j}, "_score": 1.0, "highlight": {"content": [f"{text_id}-{j}"]}}
                        for j in juans
                    ],
                }
            }
        },
    }


def _fake_es(works: list[dict], bodies: dict[tuple[int, int], str], total_works: int | None = None) -> AsyncMock:
    async def search(index: str, body: dict, **_: object) -> dict:
        if "collapse" in body:
            n = len(works) if total_works is None else total_works
            return {"hits": {"hits": works}, "aggregations": {"total_works": {"value": n}, "total_juans": {"value": n}}}
        hits = [
            {"_source": {"text_id": t, "juan_num": j, "content": c}}
            for (t, j), c in bodies.items()
        ]
        return {"hits": {"hits": hits}}

    es = AsyncMock()
    es.search.side_effect = search
    return es


@pytest.mark.asyncio
async def test_passage_across_a_hard_wrap_is_found() -> None:
    # 原文在「住」「而」之间换行；选区（已合并成一行）里没有换行
    es = _fake_es([_work(7, [1])], {(7, 1): "須菩提！應無所住\n而生其心。"})
    out = await search_content(es, "應無所住而生其心", phrase=True)
    assert [w["text_id"] for w in out["results"]] == [7]
    assert out["total"] == 1 and out["total_capped"] is False


@pytest.mark.asyncio
async def test_bag_hit_without_the_passage_is_dropped() -> None:
    # 二元组词袋会把「字差不多」的卷也粗筛进来；逐字核对必须剔掉
    es = _fake_es(
        [_work(7, [1]), _work(9, [3])],
        {(7, 1): "應無所住而生其心", (9, 3): "應無所住，而生清淨心"},
    )
    out = await search_content(es, "應無所住而生其心", phrase=True)
    assert [w["text_id"] for w in out["results"]] == [7]


@pytest.mark.asyncio
async def test_only_verified_juans_are_kept_and_lead() -> None:
    # 作品的首卷没有这段、第 5 卷有：结果要指向第 5 卷，而不是粗筛排第一的卷
    es = _fake_es([_work(7, [2, 5])], {(7, 2): "無關", (7, 5): "色即是空，空即是色"})
    (work,) = (await search_content(es, "色即是空 空即是色", phrase=True))["results"]
    assert work["juan_num"] == 5
    assert [j["juan_num"] for j in work["matched_juans"]] == [5]
    assert work["matched_juan_count"] == 1
    assert work["highlight"] == ["7-5"]


@pytest.mark.asyncio
async def test_traditional_and_simplified_match_each_other() -> None:
    es = _fake_es([_work(7, [1])], {(7, 1): "一切有為法，如夢幻泡影"})
    out = await search_content(es, "一切有为法 如梦幻泡影", phrase=True)
    assert out["total"] == 1


@pytest.mark.asyncio
async def test_total_is_flagged_as_lower_bound_past_the_candidate_cap() -> None:
    es = _fake_es([_work(7, [1])], {(7, 1): "如是我聞"}, total_works=PHRASE_CANDIDATE_WORKS + 1)
    out = await search_content(es, "如是我聞", phrase=True)
    assert out["total"] == 1 and out["total_capped"] is True


@pytest.mark.asyncio
async def test_phrase_mode_keeps_lang_filter() -> None:
    es = _fake_es([], {})
    await search_content(es, "如是我聞", lang="lzh", phrase=True)
    query = es.search.await_args_list[0].kwargs["body"]["query"]
    assert query["bool"]["filter"] == [{"term": {"lang": "lzh"}}]


@pytest.mark.asyncio
async def test_phrase_mode_with_no_usable_clause_skips_es() -> None:
    es = _fake_es([], {})
    out = await search_content(es, "空。", phrase=True)
    assert out["total"] == 0 and out["results"] == []
    es.search.assert_not_called()


@pytest.mark.asyncio
async def test_default_mode_is_unchanged_plain_match() -> None:
    es = AsyncMock()
    es.search.return_value = {"hits": {"hits": []}, "aggregations": {}}
    await search_content(es, "應無所住而生其心")
    query = es.search.await_args.kwargs["body"]["query"]
    # 默认模式仍是普通 match（不是短语）；4 字以上另加「夹注逐字含整句」的 0 分补漏（不改排序）
    assert query == {
        "bool": {
            "should": [
                {"match": {"content": {"query": "應無所住而生其心", "analyzer": "cjk_content"}}},
                {
                    "constant_score": {
                        "filter": {"match_phrase": {"notes": {"query": "應無所住而生其心", "analyzer": "cjk_content"}}},
                        "boost": 0.0,
                    }
                },
            ],
            "minimum_should_match": 1,
        }
    }


def _cworked(text_id: int, cbeta_id: str, juan: int = 1) -> dict:
    w = _work(text_id, [juan])
    w["_source"]["cbeta_id"] = cbeta_id
    return w


def _two_pool_es(bm25: list[dict], canon: list[dict], bodies: dict[tuple[int, int], str]) -> AsyncMock:
    """BM25 pool = no ``sort``; canon-order pool = script sort (see _run_content_search)."""

    async def search(index: str, body: dict, **_: object) -> dict:
        if "collapse" in body:
            works = canon if "sort" in body else bm25
            n = len(works)
            return {"hits": {"hits": works}, "aggregations": {"total_works": {"value": n}, "total_juans": {"value": n}}}
        hits = [{"_source": {"text_id": t, "juan_num": j, "content": c}} for (t, j), c in bodies.items()]
        return {"hits": {"hits": hits}}

    es = AsyncMock()
    es.search.side_effect = search
    return es


@pytest.mark.asyncio
async def test_source_outranked_by_commentaries_is_still_found_and_leads() -> None:
    # 生产 2026-11-15：「應無所住而生其心」BM25 下《金剛經》T0235 排第 40，前 30 全是注疏，
    # 逐字核对的候选里根本没有它。按藏经编号的那组候选把它带回来，并排在注疏前面。
    passage = "應無所住而生其心"
    commentaries = [_cworked(500 + i, f"X{468 + i:04d}") for i in range(3)]
    bodies = {(w["_source"]["text_id"], 1): f"注云{passage}也" for w in commentaries}
    bodies[(7, 1)] = "不應住聲香味觸法生心，應無所\n住而生其心。"
    es = _two_pool_es(bm25=commentaries, canon=[_cworked(7, "T0235"), *commentaries], bodies=bodies)

    out = await search_content(es, passage, phrase=True)

    assert [w["cbeta_id"] for w in out["results"]] == ["T0235", "X0468", "X0469", "X0470"]
    canon_bodies = [c.kwargs["body"] for c in es.search.await_args_list if "sort" in c.kwargs["body"]]
    assert len(canon_bodies) == 1 and canon_bodies[0]["track_scores"] is True
    # 按编号那组必须是精确匹配：用词袋的话，最靠前的几部会被「字差不多」的早期经占满，原典又被挤掉
    assert canon_bodies[0]["query"]["bool"]["must"] == [{"match_phrase": {"content.nopunct": {"query": passage}}}]
    assert canon_bodies[0]["size"] == PHRASE_CANON_WORKS


@pytest.mark.asyncio
async def test_work_in_both_pools_is_listed_once() -> None:
    es = _two_pool_es(
        bm25=[_cworked(7, "T0235")], canon=[_cworked(7, "T0235")], bodies={(7, 1): "應無所住而生其心"}
    )
    out = await search_content(es, "應無所住而生其心", phrase=True)
    assert [w["text_id"] for w in out["results"]] == [7]
