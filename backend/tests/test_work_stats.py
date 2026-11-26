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


def test_writing_requirements_are_not_stats_questions():
    # 2026-11-26 回放生产历史提问：这些含「字数/篇幅」但不是在问经的篇幅
    for q in (
        "举个生活实例说明「以无常观，珍惜当下」，字数在300字左右",
        "请重新生成，字数不少于2000字",
        "由于整体篇幅受限，我只能准备1-2页的PPT",
        "选取一位禅师阐述其主要禅法思想。字数不限",
        "整理成一个表格，表格包括：论中的原文，消文，出处（第几卷）",
    ):
        assert not ws.has_stats_intent(q), q
    for q in ("80卷华严每卷字数", "诵一部解深密经多少字", "阿含经多少卷", "普贤行愿品一共多少字"):
        assert ws.has_stats_intent(q), q


def test_short_names_without_jing_lun():
    assert ws._SHORT_ALIASES["俱舍"] == "俱舍论"
    assert ws._SHORT_ALIASES["法华"] == "法华经"
    # 品名不当整部经：问「普贤行愿品多少字」给 40 卷的数会被当成那一品的数
    assert not any(k.endswith("品") or v.endswith("品") for k, v in ws._SHORT_ALIASES.items())
    assert all(len(k) >= 2 for k in ws._SHORT_ALIASES)
    assert ws._EXTRA_ALIASES["华严"] == ("T0278", "T0279", "T0293")


def test_juan_hint():
    assert ws.juan_hint("80卷华严每卷字数") == 80
    assert ws.juan_hint("八十卷華嚴") == 80
    assert ws.juan_hint("四十卷本") == 40
    assert ws.juan_hint("六十卷") == 60
    assert ws.juan_hint("华严经有几卷") is None


def test_common_names_far_from_formal_titles():
    # 22 部常问经论实测里没认出的 5 部（正式题名与通俗叫法差得远）
    for name in ("无量寿经", "药师经", "维摩经", "楞伽经", "中论"):
        assert name in ws._EXTRA_ALIASES, name
    assert ws._EXTRA_ALIASES["楞伽经"] == ("T0670", "T0671", "T0672")


def test_fold_avoids_one_to_many_traditional_forms():
    # 简转繁会把「占察」转成「佔察」，经名却是「占」；在简体空间比就不会错
    assert ws.fold("占察善惡業報經") == ws.fold("占察善恶业报经")
    assert ws.fold("阿毘達磨大毘婆沙論") == ws.fold("阿毗达摩大毗婆沙论")


_INDEX = [
    (ws.fold("占察善惡業報經"), 1),
    (ws.fold("占察善惡業報經玄義"), 2),
    (ws.fold("佛說無量壽經"), 3),
    (ws.fold("大方廣佛華嚴經"), 4),
    (ws.fold("華嚴經"), 5),
]


def test_match_bracketed_name_exactly():
    assert ws._match_name(_INDEX, "占察善恶业报经") == [1]  # 不带出注疏《玄義》
    assert ws._match_name(_INDEX, "无量寿经") == [3]  # 可省「佛说」


def test_match_full_title_in_question_keeps_longest():
    ids, longest = ws._match_in_question(_INDEX, "80卷大方廣佛華嚴經共有多少字")
    assert ids == [4] and longest == 7
    ids, _ = ws._match_in_question(_INDEX, "占察善恶业报经有多少字")
    assert ids == [1]
