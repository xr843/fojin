"""全文检索也搜夹注：命中夹注的片段加括号接在正文片段后面（阅读页里夹注也是括号小字）。"""

from unittest.mock import AsyncMock

from app.services.search import search_content


async def test_note_fragments_follow_content_fragments_in_brackets():
    hit = {
        "_source": {"text_id": 75, "cbeta_id": "T2128", "title_zh": "一切經音義", "juan_num": 5},
        "_score": 3.0,
        "highlight": {"content": ["<em>骸骨</em>。"], "notes": ["<em>上戶皆反</em>公羊傳云"]},
        "inner_hits": {"matched_juans": {"hits": {"total": {"value": 1}, "hits": [
            {"_source": {"juan_num": 5}, "_score": 3.0, "highlight": {"notes": ["<em>上戶皆反</em>"]}},
        ]}}},
    }  # fmt: skip
    es = AsyncMock()
    es.search.return_value = {"hits": {"hits": [hit]}, "aggregations": {"total_works": {"value": 1}}}
    out = await search_content(es, "上戶皆反")
    r = out["results"][0]
    assert r["highlight"] == ["<em>骸骨</em>。", "（<em>上戶皆反</em>公羊傳云）"]
    assert r["matched_juans"][0]["highlight"] == ["（<em>上戶皆反</em>）"]
    body = es.search.await_args.kwargs["body"]
    assert "notes" in body["highlight"]["fields"]
