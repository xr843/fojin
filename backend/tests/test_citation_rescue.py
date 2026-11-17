"""citation_rescue：检索没调出、但引文逐字出自所引之书的引用，要在护栏之前补上来源。

生产 2026-11-16：30 天 124 处「书名核不上」里 36 处引文经 /verify/quote 确认逐字出自
模型说的那部书——引用是对的，只是检索没把书调出来，护栏去掉了可点击出处。
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import app.services.citation_rescue as cr
from app.schemas.chat import ChatSource
from app.schemas.verification import QuoteMatch, QuoteVerdict
from app.services.citation_guard import _norm_title, enforce_citation_whitelist
from app.services.quote_verifier import verify_quoted_content


def _src(text_id: int, title: str, juan: int, text: str = "…") -> ChatSource:
    return ChatSource(text_id=text_id, juan_num=juan, chunk_index=0, chunk_text=text, score=0.9, title_zh=title)


def _verdict(quote: str, *, text_id: int, title: str, juan: int, matched: bool = True) -> QuoteVerdict:
    return QuoteVerdict(
        quote=quote, normalised_quote=quote, verbatim=matched, bucket="exact" if matched else "absent",
        similarity=1.0 if matched else 0.3,
        matches=[QuoteMatch(text_id=text_id, cbeta_id="X", title_zh=title, juan_num=juan)] if matched else [],
        cite_resolved=True, cite_matched=matched,
    )


# 键用生产同一个 _norm_title 生成（繁简转换不会把「毘」转成「毗」，手写简体键会对不上）
INDEX = {
    _norm_title("修習止觀坐禪法要"): [cr._Part(1915, "T1915", None, None)],
    _norm_title("阿毘達磨俱舍論"): [cr._Part(38, "T1558", None, None)],
    _norm_title("大般若波羅蜜多經(第1卷-第200卷)"): [cr._Part(10006, "T0220a", 1, 200), cr._Part(10008, "T0220c", 401, 600)],
}


@pytest.fixture(autouse=True)
def _index(monkeypatch):
    monkeypatch.setattr(cr, "_title_index", AsyncMock(return_value=INDEX))


@pytest.mark.asyncio
async def test_verbatim_quote_in_named_text_is_rescued_and_survives_the_guard(monkeypatch):
    quote = "依因此戒，得生諸禪定，及滅苦智慧"
    vq = AsyncMock(return_value=_verdict(quote, text_id=1915, title="修習止觀坐禪法要", juan=1))
    monkeypatch.setattr(cr, "verify_quote", vq)
    answer = f"智者大师说：「{quote}」【《修習止觀坐禪法要》第1卷】。"
    retrieved = [_src(7, "金剛般若波羅蜜經", 1)]

    extra = await cr.rescue_unretrieved_citations(answer, retrieved, db=None, es=None)

    assert [(s.text_id, s.juan_num, s.chunk_index) for s in extra] == [(1915, 1, -1)]
    assert vq.await_args.kwargs["cite"] == "T1915"
    # 护栏放行（不再去掉链接），引文核验也认它
    sources = [*retrieved, *extra]
    out, muts = enforce_citation_whitelist(answer, sources)
    assert muts == [] and out == answer
    _, qmuts = verify_quoted_content(out, sources)
    assert qmuts == []


@pytest.mark.asyncio
async def test_wrong_fascicle_is_corrected_to_where_the_quote_actually_is(monkeypatch):
    quote = "諸有漏慧皆智性攝"
    monkeypatch.setattr(cr, "verify_quote", AsyncMock(return_value=_verdict(quote, text_id=38, title="阿毘達磨俱舍論", juan=26)))
    answer = f"「{quote}」【《阿毘達磨俱舍論》第3卷】"
    extra = await cr.rescue_unretrieved_citations(answer, [], db=None, es=None)
    out, muts = enforce_citation_whitelist(answer, extra)
    assert [m.kind for m in muts] == ["fascicle_corrected"]
    assert "第26卷" in out


@pytest.mark.asyncio
async def test_quote_not_in_the_named_text_is_not_rescued(monkeypatch):
    # 生产 B 类：引文是真经文，但出自别的书（书名标错）——不能替它补来源
    quote = "住中無表初成現在，初剎那後成過、現二世也"
    monkeypatch.setattr(cr, "verify_quote", AsyncMock(return_value=_verdict(quote, text_id=38, title="阿毘達磨俱舍論", juan=13, matched=False)))
    answer = f"「{quote}」【《阿毘達磨俱舍論》第13卷】"
    assert await cr.rescue_unretrieved_citations(answer, [], db=None, es=None) == []
    _, muts = enforce_citation_whitelist(answer, [])
    assert [m.kind for m in muts] == ["unverified_title"]


@pytest.mark.asyncio
async def test_nothing_to_check_without_a_long_enough_quote_or_known_title(monkeypatch):
    vq = AsyncMock()
    monkeypatch.setattr(cr, "verify_quote", vq)
    cases = [
        "如《修習止觀坐禪法要》所說【《修習止觀坐禪法要》第1卷】。",  # 没有引文
        "「止觀二法」【《修習止觀坐禪法要》第1卷】",  # 引文太短（4 字）
        "「某某某某某某某某某某」【《不存在的書》第1卷】",  # 书名不在库里
        "「依因此戒，得生諸禪定」【《金剛般若波羅蜜經》第1卷】",  # 书已在检索结果里，护栏会自己处理
    ]
    for answer in cases:
        assert await cr.rescue_unretrieved_citations(answer, [_src(7, "金剛般若波羅蜜經", 1)], db=None, es=None) == []
    vq.assert_not_awaited()


@pytest.mark.asyncio
async def test_split_work_checks_the_part_that_holds_the_cited_fascicle(monkeypatch):
    quote = "復次善現，菩薩摩訶薩修行般若"
    vq = AsyncMock(return_value=_verdict(quote, text_id=10008, title="大般若波羅蜜多經(第401卷-第600卷)", juan=403))
    monkeypatch.setattr(cr, "verify_quote", vq)
    extra = await cr.rescue_unretrieved_citations(f"「{quote}」【《大般若波罗蜜多经》第403卷】", [], db=None, es=None)
    assert vq.await_args.kwargs["cite"] == "T0220c"
    assert [(s.text_id, s.juan_num) for s in extra] == [(10008, 403)]
    # 分段的书不给卷号就无法判断查哪一段 → 不查
    vq.reset_mock()
    assert await cr.rescue_unretrieved_citations(f"「{quote}」【《大般若波罗蜜多经》】", [], db=None, es=None) == []
    vq.assert_not_awaited()


CANDIDATE = "「依因此戒，得生諸禪定，及滅苦智慧」【《修習止觀坐禪法要》第1卷】"


@pytest.mark.asyncio
async def test_rescue_failure_or_timeout_leaves_sources_untouched(monkeypatch):
    import app.services.chat as chat

    retrieved = [_src(7, "金剛般若波羅蜜經", 1)]

    class _S:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *a):
            return False

    async def boom(*a, **k):
        raise RuntimeError("es down")

    monkeypatch.setattr(chat, "rescue_unretrieved_citations", boom)
    monkeypatch.setattr(chat, "get_es", lambda: None)
    assert await chat._with_rescued_sources(CANDIDATE, retrieved, lambda: _S()) is retrieved

    async def slow(*a, **k):
        import asyncio
        await asyncio.sleep(10)

    monkeypatch.setattr(chat, "rescue_unretrieved_citations", slow)
    monkeypatch.setattr(chat, "RESCUE_TIMEOUT_S", 0.05)
    assert await chat._with_rescued_sources(CANDIDATE, retrieved, lambda: _S()) is retrieved


def test_answers_without_candidates_never_open_a_db_session():
    # 大多数回答没有要补救的引用：不能为它们占一个连接池槽位（流式路径的会话约定）
    import asyncio

    import app.services.chat as chat

    opened = []
    retrieved = [_src(7, "金剛般若波羅蜜經", 1)]
    for answer in ["没有引用的回答。", "「依因此戒，得生諸禪定」【《金剛般若波羅蜜經》第1卷】", "「短句」【《修習止觀坐禪法要》】"]:
        out = asyncio.run(chat._with_rescued_sources(answer, retrieved, lambda: opened.append(1)))
        assert out is retrieved
    assert opened == []
