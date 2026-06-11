"""Tests for 本经召回保底 root-sutra detection (rag_retrieval._detect_named_root).

The reserved-slot injection itself needs a live pgvector corpus and is verified
against prod; here we lock the pure name→root-cbeta_id mapping that gates it.
"""

import pytest

from app.services.rag_retrieval import _detect_named_root


@pytest.mark.parametrize(
    "query,expected",
    [
        # Conversational queries naming a sutra (the failure mode that motivated this).
        ("心经的核心思想是什么", "T0251"),
        ("心經講什麼", "T0251"),
        ("般若波罗蜜多心经讲的空是什么意思", "T0251"),
        ("金刚经为什么说应无所住而生其心", "T0235"),
        ("金剛經的四句偈", "T0235"),
        ("法华经的一佛乘", "T0262"),
        ("观世音菩萨普门品", "T0262"),
        ("阿弥陀经怎么念", "T0366"),
        ("地藏经讲因果", "T0412"),
        ("楞严经的二十五圆通", "T0945"),
        ("楞伽经与唯识", "T0670"),
        ("六祖坛经的顿悟", "T2008"),
    ],
)
def test_named_sutra_maps_to_root(query, expected):
    assert _detect_named_root(query) == expected


def test_longest_match_disambiguates_nested_names():
    # "观无量寿经" (T0365) must win over the nested "无量寿经" (T0360).
    assert _detect_named_root("观无量寿经的十六观") == "T0365"
    # bare 无量寿经 still resolves to T0360.
    assert _detect_named_root("无量寿经的四十八愿") == "T0360"


def test_no_false_positive_when_no_sutra_named():
    assert _detect_named_root("什么是缘起性空") is None
    assert _detect_named_root("禅宗和净土宗的区别") is None
    assert _detect_named_root("") is None


@pytest.mark.parametrize(
    "query",
    [
        # 心 + 经济/经验/经常/经过 — the 经 belongs to a following compound, not 心經.
        "担心经济压力如何修行",
        "关心经济与布施的关系",
        "修心经验怎么积累",
        "开心经常念佛好吗",
        "小心经过这段路",
        # 坛 + 经历/经验 — 论坛|经历, not 六祖坛经.
        "论坛经历分享",
        "花坛经过修整",
    ],
)
def test_ambiguous_short_alias_rejects_jing_compound(query):
    assert _detect_named_root(query) is None


def test_ambiguous_alias_still_matches_real_reference():
    # The guard must not suppress genuine references where 经 is the sutra's.
    assert _detect_named_root("讲讲心经") == "T0251"
    assert _detect_named_root("心经全文") == "T0251"
    assert _detect_named_root("担心经济，但还是想读心经") == "T0251"  # 2nd occurrence is real
    assert _detect_named_root("六祖坛经讲顿悟") == "T2008"


# --- Case 2: doctrine-term → foundational-text mapping ----------------------

from app.services.rag_retrieval import _detect_doctrine_root


@pytest.mark.parametrize(
    "query,expected",
    [
        # 中观
        ("什么是缘起性空", "T1564"),
        ("空性怎么理解", "T1564"),
        ("畢竟空與斷滅見的區別", "T1564"),
        # 唯识
        ("唯识学的三自性", "T1585"),
        ("阿赖耶识是什么", "T1585"),
        ("轉識成智的過程", "T1585"),
        # 佛性
        ("一切众生皆有佛性吗", "T0374"),
        ("如来藏思想", "T0374"),
        # 天台
        ("一念三千怎么理解", "T1911"),
        ("一心三觀的修法", "T1911"),
        # 华严
        ("事事无碍法界", "T0279"),
        ("因陀羅網的比喻", "T0279"),
        # 净土
        ("净土法门适合我吗", "T0366"),
        ("帶業往生可能嗎", "T0366"),
        # 禅宗
        ("顿悟和渐修的区别", "T2008"),
        ("如何明心见性", "T2008"),
        # 不二 / 法华 / 根本教义
        ("什么是不二法门", "T0475"),
        ("一佛乘的含义", "T0262"),
        ("四圣谛和八正道", "T0099"),
        ("十二因緣流轉", "T0099"),
    ],
)
def test_doctrine_term_maps_to_foundational_text(query, expected):
    assert _detect_doctrine_root(query) == expected


def test_doctrine_longest_match_wins():
    # "缘起性空" (T1564 via 4-char term) contains "空性"? It does not — but
    # "自性空" ⊂ "缘起性空" is also absent. The real nesting risk: a query with
    # both "法界缘起" (T0279) and "缘起" — bare "缘起" is deliberately unmapped,
    # so the 4-char Huayan term must win.
    assert _detect_doctrine_root("法界缘起与十玄门") == "T0279"


def test_doctrine_no_false_positive():
    assert _detect_doctrine_root("今天天气怎么样") is None
    assert _detect_doctrine_root("怎么注册账号") is None
    assert _detect_doctrine_root("") is None
    # Bare generic words deliberately unmapped: 缘起 / 中道 / 念佛 / 止观.
    assert _detect_doctrine_root("缘起是什么") is None
    assert _detect_doctrine_root("念佛是谁") is None


def test_named_sutra_query_not_hijacked_by_doctrine_term():
    # Queries naming a sutra AND containing a doctrine term: named root must
    # win inside _inject_root_sutra_slot (named checked first). Here we just
    # pin that both detectors fire independently on such a query.
    q = "六祖坛经讲的顿悟"
    assert _detect_named_root(q) == "T2008"
    assert _detect_doctrine_root(q) == "T2008"
    q2 = "心经的空性"
    assert _detect_named_root(q2) == "T0251"
    assert _detect_doctrine_root(q2) == "T1564"
