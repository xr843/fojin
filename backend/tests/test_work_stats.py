"""问答「多少字 / 每卷字数」的收录文本统计（services/work_stats.py）。"""

import asyncio

from app.services import work_stats as ws


def test_intent_only_for_count_questions():
    assert ws.has_stats_intent("80卷大方廣佛華嚴經共有多少字？")
    assert ws.has_stats_intent("请把CBETA中80卷大方廣佛華嚴經每卷字数列表并计算总数")
    assert ws.has_stats_intent("華嚴經有幾卷")
    # 普通义理题不查
    assert not ws.has_stats_intent("华严经的法界缘起怎么理解？")
    assert not ws.has_stats_intent("请把《阿毗达磨大毗婆沙论》200卷做出结构化呈现")


def test_drop_contained_keeps_longest_title():
    assert ws._drop_contained(["大方廣佛華嚴經", "華嚴經", "佛華嚴經"]) == ["大方廣佛華嚴經"]
    assert sorted(ws._drop_contained(["俱舍論", "金剛經"])) == ["俱舍論", "金剛經"]


def test_block_says_not_scripture_and_lists_juans():
    block = ws.format_stats_block(
        [
            {
                "cbeta_id": "T0279",
                "title": "大方廣佛華嚴經",
                "translator": "實叉難陀",
                "dynasty": "唐",
                "n_juan": 2,
                "han_total": 12076,
                "raw_total": 13859,
                "juans": [(1, 5418), (2, 6658)],
            }
        ]
    )
    assert "不是经文内容" in block and "不要" in block and "【《经名》第N卷】" in block
    assert "《大方廣佛華嚴經》T0279（唐實叉難陀），2卷：汉字共 12,076 字；含标点 13,859 字。" in block
    assert "卷1 5,418；卷2 6,658" in block


def test_long_works_give_total_only():
    juans = [(i, 1000) for i in range(1, ws.MAX_JUAN_LISTED + 2)]
    block = ws.format_stats_block(
        [
            {
                "cbeta_id": "T0220a",
                "title": "大般若",
                "n_juan": len(juans),
                "han_total": 1,
                "raw_total": 1,
                "juans": juans,
            }
        ]
    )
    assert "各卷汉字数" not in block


def test_no_intent_never_touches_db():
    # db=None：没问字数就直接返回，连数据库都不碰
    assert asyncio.run(ws.lookup_work_stats(None, "华严经讲什么")) == ""


def test_incomplete_collection_is_flagged():
    block = ws.format_stats_block(
        [
            {
                "cbeta_id": "X0001",
                "title": "某經",
                "n_juan": 3,
                "expected_juan": 10,
                "han_total": 30,
                "raw_total": 40,
                "juans": [(1, 10), (2, 10), (3, 10)],
            }
        ]
    )
    assert "应有 10 卷，佛津只收录了其中 3 卷" in block


def test_split_part_pattern():
    assert ws._PART_RE.match("T0220c").group(1) == "T0220"
    assert ws._PART_RE.match("T0279") is None
