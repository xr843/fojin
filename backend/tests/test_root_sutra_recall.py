"""Tests for 本经召回保底 root detection + reserved-slot injection.

Detector tests lock the pure term→root-cbeta_id mappings; injector tests
monkeypatch the two DB awaits to pin slot placement and the cap.
"""

import pytest

from app.services import rag_retrieval
from app.services.rag_retrieval import (
    _detect_doctrine_root,
    _detect_named_root,
    _detect_phrase_root,
    _inject_root_sutra_slot,
)


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
        # 华严宗义 → 五教章 (treatise vocabulary, not sutra vocabulary)
        ("事事无碍法界", "T1866"),
        ("四法界怎么分", "T1866"),
        # …but the 帝网 imagery lives in the sutra itself
        ("因陀羅網的比喻", "T0279"),
        # 净土
        ("净土法门适合我吗", "T0366"),
        ("帶業往生可能嗎", "T0365"),
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
    # No key currently nests inside another; the longest-first sort guards
    # future additions (a bare "缘起" entry must never shadow "法界缘起").
    assert _detect_doctrine_root("法界缘起与十玄门") == "T1866"


@pytest.mark.parametrize(
    "query",
    [
        # 毕竟空 + 闲/调/气 — the 空 belongs to a following secular compound.
        "毕竟空闲时间少，怎么安排修行",
        "毕竟空调房里打坐舒服吗",
        "毕竟空气不好少出门",
        # 空性 matched across the word boundary of 真空|性质, 航空|性能.
        "真空性质和佛教的空有关系吗",
        "航空性能怎么评估",
    ],
)
def test_doctrine_cross_boundary_compound_rejected(query):
    assert _detect_doctrine_root(query) is None


def test_doctrine_ambiguous_term_still_matches_real_usage():
    assert _detect_doctrine_root("毕竟空与断灭见的区别") == "T1564"
    assert _detect_doctrine_root("何谓毕竟空") == "T1564"  # term at end of query
    assert _detect_doctrine_root("空性怎么理解") == "T1564"


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


# --- Case 3: canonical phrase → root sutra (出自哪部经 attribution) ----------


@pytest.mark.parametrize(
    "query,expected",
    [
        # 心经 distinctive phrases
        ("「色不异空，空不异色」出自哪部经？", "T0251"),
        ("照见五蕴皆空，度一切苦厄 是哪部经", "T0251"),
        ("「不生不灭，不垢不净，不增不减」出自哪部经？", "T0251"),
        ("「是诸法空相」后面的经文内容是什么？", "T0251"),
        ("色即是空 空即是色", "T0251"),
        # 金刚经 distinctive phrases
        ("「应无所住而生其心」出自哪部经？", "T0235"),
        ("「一切有为法，如梦幻泡影」的完整偈颂是什么？出自哪里？", "T0235"),
        ("若以色见我，以音声求我，是人行邪道", "T0235"),
        ("凡所有相皆是虚妄 出处", "T0235"),
        # 坛经 distinctive phrases (note: 坛经 is also named-detectable, but the
        # phrase must resolve on its own too)
        ("菩提本无树，明镜亦非台 完整偈颂", "T2008"),
        ("本来无一物，何处惹尘埃", "T2008"),
    ],
)
def test_canonical_phrase_maps_to_root(query, expected):
    assert _detect_phrase_root(query) == expected


def test_phrase_traditional_form_also_matches():
    assert _detect_phrase_root("「應無所住而生其心」出自哪部經？") == "T0235"
    assert _detect_phrase_root("色不異空，空不異色") == "T0251"


def test_phrase_no_false_positive():
    assert _detect_phrase_root("禅修怎么入门") is None
    assert _detect_phrase_root("今天天气怎么样") is None
    assert _detect_phrase_root("介绍一下佛教历史") is None
    assert _detect_phrase_root("") is None


def test_non_distinctive_dharma_terms_not_mapped():
    # 五蕴皆空 / 一切有为法 are 法数 that recur across canons + 注疏 and read as
    # doctrine, not attribution — they must NOT fire (would wrongly grab slot #1).
    # The genuinely-distinctive lines of the same sutras still carry attribution.
    assert _detect_phrase_root("什么是五蕴皆空") is None
    assert _detect_phrase_root("有为法和无为法的区别") is None
    assert _detect_phrase_root("照见五蕴皆空，度一切苦厄出自哪部经") == "T0251"
    assert _detect_phrase_root("「一切有为法，如梦幻泡影」出自哪里") == "T0235"


# --- Injector: slot placement, cap, precedence ------------------------------


def _fake_results(n: int, start_tid: int = 100) -> list[dict]:
    return [{"text_id": start_tid + i, "score": 0.9 - i * 0.01} for i in range(n)]


@pytest.fixture
def _patched_injector_deps(monkeypatch):
    """Patch the two DB awaits; record which cbeta_id got resolved."""
    resolved: dict[str, str] = {}

    async def fake_resolve(db, cbeta_id):
        resolved["cbeta_id"] = cbeta_id
        return 999

    async def fake_search(db, emb, limit=1, scope_text_ids=None, **kw):
        return [{"text_id": scope_text_ids[0], "score": 0.42}]

    monkeypatch.setattr(rag_retrieval, "_resolve_root_text_id", fake_resolve)
    monkeypatch.setattr(rag_retrieval, "similarity_search", fake_search)
    return resolved


@pytest.mark.anyio
async def test_named_root_takes_slot_one_and_caps_at_five(_patched_injector_deps):
    out = await _inject_root_sutra_slot(None, "心经的核心思想", [0.0], _fake_results(5))
    assert len(out) == 5
    assert out[0]["text_id"] == 999  # root at slot #1
    assert _patched_injector_deps["cbeta_id"] == "T0251"


@pytest.mark.anyio
async def test_doctrine_root_takes_last_slot_and_caps_at_five(_patched_injector_deps):
    out = await _inject_root_sutra_slot(None, "什么是空性", [0.0], _fake_results(5))
    assert len(out) == 5
    assert out[-1]["text_id"] == 999  # root at LAST slot
    assert out[0]["text_id"] == 100  # reranked top hit untouched
    assert 104 not in [r["text_id"] for r in out]  # hit #5 displaced
    assert _patched_injector_deps["cbeta_id"] == "T1564"


@pytest.mark.anyio
async def test_named_wins_over_doctrine_on_mixed_query(_patched_injector_deps):
    # "心经的空性" names a sutra AND contains a doctrine term: named must win.
    out = await _inject_root_sutra_slot(None, "心经的空性", [0.0], _fake_results(3))
    assert out[0]["text_id"] == 999
    assert _patched_injector_deps["cbeta_id"] == "T0251"


@pytest.mark.anyio
async def test_root_already_present_is_noop(_patched_injector_deps):
    results = [*_fake_results(4), {"text_id": 999, "score": 0.5}]
    out = await _inject_root_sutra_slot(None, "什么是空性", [0.0], results)
    assert out == results


@pytest.mark.anyio
async def test_doctrine_with_empty_results_returns_just_root(_patched_injector_deps):
    out = await _inject_root_sutra_slot(None, "什么是空性", [0.0], [])
    assert [r["text_id"] for r in out] == [999]


@pytest.mark.anyio
async def test_no_detection_is_noop(_patched_injector_deps):
    results = _fake_results(5)
    out = await _inject_root_sutra_slot(None, "今天天气怎么样", [0.0], results)
    assert out == results
    assert "cbeta_id" not in _patched_injector_deps


@pytest.mark.anyio
async def test_phrase_attribution_takes_slot_one(_patched_injector_deps):
    # "「色不异空」出自哪部经" names no sutra, but the quote IS the answer's source,
    # so the root takes slot #1 (named tier), not the doctrine last slot.
    out = await _inject_root_sutra_slot(None, "「色不异空」出自哪部经", [0.0], _fake_results(5))
    assert len(out) == 5
    assert out[0]["text_id"] == 999
    assert _patched_injector_deps["cbeta_id"] == "T0251"
