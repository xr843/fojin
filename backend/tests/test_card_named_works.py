"""卡片题点名经论保底：模板里《》点名的经论各在检索结果里保底一个槽。

2026-10-15 审计：200 张卡片里 119 张点名的经论检索一部都带不回来，模型拿着
「附原典引用」的要求却没有原文，在思考里反复权衡，首字慢、答案只能转述。
"""

import inspect

import pytest

from app.services import chat
from app.services import named_works as NW
from app.services import rag_retrieval as R


def _chunk(text_id: int, title_zh: str, score: float = 0.6) -> dict:
    return {
        "text_id": text_id,
        "juan_num": 1,
        "chunk_index": 0,
        "chunk_text": "片段内容",
        "score": score,
        "title_zh": title_zh,
        "lang": "lzh",
        "source_id": None,
        "cbeta_id": f"T{text_id:04d}",
    }


# ── 抽取 ──────────────────────────────────────────────────────────


def test_extract_takes_head_before_middle_dot_and_dedupes_in_order():
    tmpl = "【经典】《中阿含经·念处经》与《清净道论》\n参照《中阿含经·因品》，并引《清净道论》《成佛之道》。"
    assert NW.extract_named_works(tmpl) == ["中阿含经", "清净道论", "成佛之道"]


def test_extract_skips_single_char_and_empty():
    assert NW.extract_named_works("见《疏》与《》") == []
    assert NW.extract_named_works("") == []


# ── 解析 ──────────────────────────────────────────────────────────


class _FakeDB:
    """按 SQL 参数回答：cbeta_id 列表或精确题名。记下查过的题名。"""

    def __init__(self, by_cbeta: dict[str, int], by_title: dict[str, list[int]]):
        self.by_cbeta, self.by_title, self.titles_tried = by_cbeta, by_title, []

    async def execute(self, stmt, params):
        if "c" in params:
            return [(self.by_cbeta[c],) for c in params["c"] if c in self.by_cbeta]
        self.titles_tried.append(params["t"])
        return [(i,) for i in self.by_title.get(params["t"], [])]


@pytest.fixture(autouse=True)
def _clear_cache():
    NW._cache.clear()
    yield
    NW._cache.clear()


@pytest.mark.asyncio
async def test_alias_maps_short_name_to_canonical_text_not_commentary():
    # 前缀匹配会把「俱舍论」解析成《俱舍論記》；别名表必须指向本论 T1558。
    db = _FakeDB({"T1558": 7, "T1821": 99}, {})
    assert await NW.resolve_named_work(db, "俱舍论") == (7,)
    assert db.titles_tried == []


@pytest.mark.asyncio
async def test_exact_title_tries_variant_chars_after_s2t():
    # 十住毗婆沙论 → s2t 得「十住毗婆沙論」查不到 → 异体字「毘」命中。
    db = _FakeDB({}, {"十住毘婆沙論": [21]})
    assert await NW.resolve_named_work(db, "十住毗婆沙论") == (21,)
    assert db.titles_tried == ["十住毗婆沙論", "十住毘婆沙論"]


@pytest.mark.asyncio
async def test_unresolved_is_empty_and_never_prefix_matched():
    db = _FakeDB({}, {"俱舍論記": [99]})
    assert await NW.resolve_named_work(db, "成佛之道") == ()
    assert db.titles_tried == ["成佛之道", "佛說成佛之道"]


# ── 注入 ──────────────────────────────────────────────────────────


def _install(monkeypatch, resolved: dict[str, tuple[int, ...]], scoped_hits: dict[int, dict]):
    async def _resolve(db, name):
        return resolved.get(name, ())

    async def _search(db, emb, limit=5, scope_text_ids=None, lang_list=None):
        hits = [scoped_hits[i] for i in scope_text_ids or [] if i in scoped_hits]
        return hits[:limit]

    monkeypatch.setattr(R, "resolve_named_work", _resolve)
    monkeypatch.setattr(R, "similarity_search", _search)


@pytest.mark.asyncio
async def test_named_works_go_first_and_present_ones_are_not_duplicated(monkeypatch):
    base = [_chunk(i, f"其他{i}") for i in range(1, 6)]
    _install(
        monkeypatch,
        {"中阿含经": (26,), "其他三": (3,)},
        {26: _chunk(26, "中阿含經", 0.3), 3: _chunk(3, "其他3")},
    )
    out = await R._inject_named_work_slots(object(), ["中阿含经", "其他三", "成佛之道"], [0.0], base)
    assert [r["text_id"] for r in out] == [26, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_at_most_three_named_and_two_slots_left_for_retrieval(monkeypatch):
    base = [_chunk(i, f"其他{i}") for i in range(1, 6)]
    names = ["甲经", "乙经", "丙经", "丁经"]
    ids = {n: (100 + k,) for k, n in enumerate(names)}
    _install(monkeypatch, ids, {100 + k: _chunk(100 + k, n) for k, n in enumerate(names)})
    out = await R._inject_named_work_slots(object(), names, [0.0], base)
    assert [r["text_id"] for r in out] == [100, 101, 102, 1, 2]


@pytest.mark.asyncio
async def test_nothing_resolved_leaves_results_untouched(monkeypatch):
    base = [_chunk(i, f"其他{i}") for i in range(1, 6)]
    _install(monkeypatch, {}, {})
    assert await R._inject_named_work_slots(object(), ["成佛之道"], [0.0], base) is base


# ── 接线 ──────────────────────────────────────────────────────────


@pytest.fixture
def stub_pipeline(monkeypatch):
    import contextlib

    async def _no_precise(db, query, *, scope_text_ids=None):
        return None

    async def _embed(text):
        return [0.0] * 8

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield object()

    async def _empty(*a, **k):
        return []

    async def _noop(*a, **k):
        return None

    async def _no_dict(db, query):
        return ""

    async def _no_root(db, query, emb, results):
        return results

    monkeypatch.setattr(R, "try_precise_text_retrieval", _no_precise)
    monkeypatch.setattr(R, "generate_embedding", _embed)
    monkeypatch.setattr(R, "async_session", _fake_session)
    monkeypatch.setattr(R, "source_similarity_search", _empty)
    monkeypatch.setattr(R, "_attach_parallel_chunks", _noop)
    monkeypatch.setattr(R, "_attach_mitra_parallels", _noop)
    monkeypatch.setattr(R, "_lookup_dictionary_terms", _no_dict)
    monkeypatch.setattr(R, "_inject_root_sutra_slot", _no_root)

    async def _resolve(db, name):
        return {"中阿含经": (26,)}.get(name, ())

    pool = [_chunk(i, f"其他{i}") for i in range(1, 8)]

    async def _search(db, emb, limit=5, scope_text_ids=None, lang_list=None):
        if scope_text_ids == [26]:
            return [_chunk(26, "中阿含經", 0.3)]
        if lang_list in (["pi"], ["bo"]):
            return []
        return pool[:limit]

    monkeypatch.setattr(R, "resolve_named_work", _resolve)
    monkeypatch.setattr(R, "similarity_search", _search)


@pytest.mark.asyncio
async def test_retrieve_rag_context_serves_named_work(stub_pipeline):
    sources, context = await R.retrieve_rag_context(object(), "《念处经》四念处如何实修？", named_works=["中阿含经"])
    assert sources[0].title_zh == "中阿含經"
    assert "《中阿含經》" in context


@pytest.mark.asyncio
async def test_retrieve_rag_context_without_named_works_is_unchanged(stub_pipeline):
    sources, _ = await R.retrieve_rag_context(object(), "《念处经》四念处如何实修？")
    assert all(s.title_zh != "中阿含經" for s in sources)


def test_prepare_chat_passes_card_named_works_to_retrieval():
    src = inspect.getsource(chat._prepare_chat)
    assert src.count("card_named_works = extract_named_works(hq[1])") == 1
    assert "named_works=card_named_works" in src
