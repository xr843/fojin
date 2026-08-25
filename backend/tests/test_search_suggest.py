"""``/search/suggest``：首页与搜索页的联想。

2026-08-25 生产实测：输入「金刚」出来的是 金刚 / 金刚石 / 金刚砂 / 金刚宝石 / 金刚怒目
（辞典词头按长度排在最前），再是几部密教仪轨 —— 全站最热的《金刚经》根本不在列；
「心经」也不出《般若波罗蜜多心经》。原因是标题联想只做 match_phrase_prefix，而辞典
词头永远排第一。

这里锁四件事：
1. 别名命中（services/search.py 的 _SUTRA_ABBREV，与问答/搜索共用一张表）的正典
   经名排最前 —— 「金刚」「金刚经」「心经」都要先出本经。
2. 辞典**精确**词头紧随其后（「苦」仍要先看到词条「苦」，而不是以苦开头的经名），
   辞典前缀词头（金刚石…）退到经名之后。
3. 每条带 type（title / term / question），前端据此分组；``suggestions`` 仍是纯字符串
   列表（搜索页旧消费方不变）。
4. 去重、封顶 10。

``client`` fixture 把 get_db 覆盖成 yield None，辞典/热门问题那两条 DB 查询走
_dict_suggestions / _hot_question_suggestions，这里直接 patch。
"""

from unittest.mock import AsyncMock, patch

import pytest

ES_TITLES = ["金剛頂瑜伽理趣般若經", "金剛頂瑜伽中略出念誦經"]


@pytest.fixture
def suggest_patches():
    with (
        patch("app.api.search.get_suggestions", new_callable=AsyncMock, return_value=ES_TITLES) as es,
        patch(
            "app.api.search._dict_suggestions",
            new_callable=AsyncMock,
            return_value=(["金刚"], ["金刚石", "金刚砂", "金刚宝石"]),
        ) as dict_,
        patch(
            "app.api.search._hot_question_suggestions",
            new_callable=AsyncMock,
            return_value=["《金刚经》四句偈的真正含义是什么？"],
        ) as hot,
    ):
        yield es, dict_, hot


async def test_alias_canonical_title_comes_first(client, suggest_patches) -> None:
    resp = await client.get("/api/search/suggest", params={"q": "金刚"})
    assert resp.status_code == 200
    body = resp.json()
    items = body["items"]
    assert items[0] == {"value": "金剛般若波羅蜜經", "type": "title"}
    # 精确词头第二，ES 标题随后，前缀词头退到经名之后，热门问题垫底
    values = [i["value"] for i in items]
    assert values.index("金刚") == 1
    assert values.index("金剛頂瑜伽理趣般若經") < values.index("金刚石")
    assert values[-1] == "《金刚经》四句偈的真正含义是什么？"
    assert body["suggestions"] == values


async def test_alias_match_is_prefix_based(client, suggest_patches) -> None:
    """「金刚经」（完整别名）与「心经」都要先出本经。"""
    resp = await client.get("/api/search/suggest", params={"q": "金刚经"})
    assert resp.json()["items"][0]["value"] == "金剛般若波羅蜜經"
    resp = await client.get("/api/search/suggest", params={"q": "心经"})
    assert resp.json()["items"][0] == {"value": "般若波羅蜜多心經", "type": "title"}


async def test_exact_headword_first_when_no_alias(client) -> None:
    """「苦」：没有别名 → 精确词头「苦」第一，而不是以苦开头的经名。"""
    with (
        patch("app.api.search.get_suggestions", new_callable=AsyncMock, return_value=["苦陰經"]),
        patch("app.api.search._dict_suggestions", new_callable=AsyncMock, return_value=(["苦"], ["苦谛", "苦集"])),
        patch("app.api.search._hot_question_suggestions", new_callable=AsyncMock, return_value=[]),
    ):
        resp = await client.get("/api/search/suggest", params={"q": "苦"})
    items = resp.json()["items"]
    assert items[0] == {"value": "苦", "type": "term"}
    assert [i["type"] for i in items] == ["term", "title", "term", "term"]


async def test_dedupes_and_caps_at_ten(client) -> None:
    with (
        patch("app.api.search.get_suggestions", new_callable=AsyncMock,
              return_value=[f"經{i}" for i in range(8)]),
        patch("app.api.search._dict_suggestions", new_callable=AsyncMock,
              return_value=(["經0"], [f"詞{i}" for i in range(8)])),
        patch("app.api.search._hot_question_suggestions", new_callable=AsyncMock,
              return_value=["問1"]),
    ):
        resp = await client.get("/api/search/suggest", params={"q": "經"})
    values = [i["value"] for i in resp.json()["items"]]
    assert len(values) == 10
    assert len(set(values)) == 10
    assert values.count("經0") == 1
