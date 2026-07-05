"""Tests for the agentic research assistant's orchestration.

The LLM (`complete`) and the corpus retriever are injected fakes, so the whole
plan → retrieve → synthesize → ground loop is exercised deterministically with
no LLM or DB. Grounding reuses the real citation_guard / quote_verifier, so a
fabricated citation in the synthesis is really caught here.
"""

import pytest

from app.schemas.chat import ChatSource, ParallelChunk
from app.schemas.research import ResearchReference
from app.services.research_agent import (
    ResearchAgent,
    build_plan_prompt,
    ground_answer,
    parse_plan,
)


def _src(text_id: int, title: str, juan: int = 1, text: str = "色不异空，空不异色。") -> ChatSource:
    return ChatSource(
        text_id=text_id, juan_num=juan, chunk_index=0, chunk_text=text,
        score=0.9, title_zh=title, urn=f"fojin:cbeta/T{text_id:04d}.{juan}",
    )


class _ScriptedLLM:
    """Returns queued responses in order; records the prompts it saw."""
    def __init__(self, *responses: str) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    async def __call__(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self._responses.pop(0) if self._responses else ""


# ── parse_plan ───────────────────────────────────────────────────────────


def test_parse_plan_reads_steps_and_caps():
    text = '{"steps":[{"query":"般若 空","aspect":"般若"},{"query":"中观 空","aspect":"中观"},{"query":"唯识 空","aspect":"唯识"}]}'
    steps = parse_plan(text, "空的三系比较", max_steps=2)
    assert len(steps) == 2                       # capped to max_steps
    assert steps[0].query == "般若 空"
    assert steps[0].aspect == "般若"
    assert steps[0].tool == "corpus"


def test_parse_plan_tolerates_code_fence_and_prose():
    text = "好的，这是计划：\n```json\n{\"steps\":[{\"query\":\"四念处\"}]}\n```\n希望有帮助"
    steps = parse_plan(text, "q", max_steps=4)
    assert len(steps) == 1
    assert steps[0].query == "四念处"


def test_parse_plan_falls_back_to_single_step_on_garbage():
    steps = parse_plan("not json at all", "如何理解空性", max_steps=4)
    assert len(steps) == 1
    assert steps[0].query == "如何理解空性"


def test_parse_plan_keeps_known_tools_and_coerces_unknown():
    steps = parse_plan(
        '{"steps":[{"query":"般若","tool":"corpus"},{"query":"空","tool":"dictionary"},'
        '{"query":"龙树","tool":"entity"},{"query":"x","tool":"web_search"}]}',
        "q", max_steps=6,
    )
    assert [s.tool for s in steps] == ["corpus", "dictionary", "entity", "corpus"]


def test_parse_plan_drops_empty_queries():
    steps = parse_plan('{"steps":[{"query":""},{"query":"  "},{"query":"真"}]}', "q", 4)
    assert len(steps) == 1
    assert steps[0].query == "真"


# ── full agent run ───────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_agent_plans_retrieves_dedupes_and_grounds():
    plan = '{"steps":[{"query":"般若 空","aspect":"般若"},{"query":"中观 空","aspect":"中观"}]}'
    # Synthesis cites a real retrieved source → survives the guard intact.
    synthesis = "般若与中观都讲空【《般若经》第1卷】。"
    llm = _ScriptedLLM(plan, synthesis)

    calls: list[str] = []

    async def corpus(query: str) -> list[ChatSource]:
        calls.append(query)
        # Both sub-queries return the same fascicle (text_id 251) + a unique one,
        # so dedup must collapse the shared one.
        shared = _src(251, "般若经")
        uniq = _src(1509 if "中观" in query else 223, "中论" if "中观" in query else "大智度论")
        return [shared, uniq]

    agent = ResearchAgent(complete=llm, corpus_tool=corpus)
    report = await agent.run("空在般若与中观如何处理", max_steps=4)

    # Planned 2 steps, both executed.
    assert calls == ["般若 空", "中观 空"]
    assert [s.query for s in report.plan] == ["般若 空", "中观 空"]
    # Shared fascicle 251 deduped: 3 distinct sources, not 4.
    ids = sorted(s.text_id for s in report.sources)
    assert ids == [223, 251, 1509]
    # Answer grounded; its single citation is to a retrieved title → verified.
    assert "【《般若经》第1卷】" in report.answer
    assert report.trust_status is not None
    assert report.trust_status.state == "verified"
    # Every source carries a URN (the #897 contract flowing through).
    assert all(s.urn for s in report.sources)


@pytest.mark.anyio
async def test_agent_strips_fabricated_citation_in_synthesis():
    plan = '{"steps":[{"query":"心经 空"}]}'
    # LLM cites a text that was NOT retrieved → guard must strip the 【】.
    synthesis = "参见【《楞严经》第5卷】的论述。"
    llm = _ScriptedLLM(plan, synthesis)

    async def corpus(query: str) -> list[ChatSource]:
        return [_src(251, "般若波罗蜜多心经")]

    report = await ResearchAgent(complete=llm, corpus_tool=corpus).run("q")
    # The fabricated citation is downgraded to plain 《》 prose.
    assert "【《楞严经》" not in report.answer
    assert "《楞严经》" in report.answer
    assert report.trust_status.state == "citation_corrected"


@pytest.mark.anyio
async def test_agent_no_sources_returns_honest_note_not_fabrication():
    llm = _ScriptedLLM('{"steps":[{"query":"x"}]}')  # synthesis LLM never called

    async def empty_corpus(query: str) -> list[ChatSource]:
        return []

    report = await ResearchAgent(complete=llm, corpus_tool=empty_corpus).run("冷僻问题")
    assert report.sources == []
    assert "未能检索到" in report.answer
    assert report.trust_status.state == "no_sources"
    # Synthesis LLM must NOT have been called (only the planner ran).
    assert len(llm.calls) == 1


@pytest.mark.anyio
async def test_agent_survives_planner_llm_failure():
    class _Boom:
        def __init__(self) -> None:
            self.calls: list[int] = []

        async def __call__(self, system, user):
            # First call (plan) raises; second (synthesis) returns text.
            self.calls.append(1)
            if len(self.calls) == 1:
                raise RuntimeError("planner down")
            return "空即是色【《般若经》第1卷】"

    async def corpus(query: str) -> list[ChatSource]:
        return [_src(251, "般若经")]

    report = await ResearchAgent(complete=_Boom(), corpus_tool=corpus).run("空性")
    # Planner failed → single-step fallback plan on the original question.
    assert len(report.plan) == 1
    assert report.plan[0].query == "空性"
    assert report.trust_status.state == "verified"


@pytest.mark.anyio
async def test_agent_survives_retrieval_failure_on_one_step():
    plan = '{"steps":[{"query":"good"},{"query":"bad"}]}'
    llm = _ScriptedLLM(plan, "答案【《般若经》第1卷】")

    async def flaky_corpus(query: str) -> list[ChatSource]:
        if query == "bad":
            raise RuntimeError("db hiccup")
        return [_src(251, "般若经")]

    report = await ResearchAgent(complete=llm, corpus_tool=flaky_corpus).run("q")
    # The failed step contributes 0 sources but doesn't sink the run.
    assert [s.num_sources for s in report.plan] == [1, 0]
    assert len(report.sources) == 1


# ── multi-tool dispatch (corpus + dictionary + entity) ───────────────────


@pytest.mark.anyio
async def test_agent_routes_steps_to_corpus_dict_and_entity():
    plan = (
        '{"steps":['
        '{"query":"空 般若","tool":"corpus","aspect":"经文"},'
        '{"query":"空","tool":"dictionary","aspect":"名相"},'
        '{"query":"龙树","tool":"entity","aspect":"人物"}]}'
    )
    llm = _ScriptedLLM(plan, "综合【《般若经》第1卷】。")
    seen = {"corpus": [], "dict": [], "entity": []}

    async def corpus(q):
        seen["corpus"].append(q)
        return [_src(251, "般若经")]

    async def dict_tool(q):
        seen["dict"].append(q)
        return [ResearchReference(kind="dictionary", term="空", detail="śūnyatā 定义", source="佛学大辞典")]

    async def entity_tool(q):
        seen["entity"].append(q)
        return [ResearchReference(kind="entity", term="龙树", detail="中观创立者", source="person")]

    report = await ResearchAgent(
        complete=llm, corpus_tool=corpus, dict_tool=dict_tool, entity_tool=entity_tool
    ).run("空性问题", max_steps=6)

    # Each step routed to the right tool.
    assert seen["corpus"] == ["空 般若"]
    assert seen["dict"] == ["空"]
    assert seen["entity"] == ["龙树"]
    # Corpus → sources (citable); dict/entity → references (background).
    assert [s.text_id for s in report.sources] == [251]
    assert {r.kind for r in report.references} == {"dictionary", "entity"}
    # Per-step counts recorded for corpus AND reference steps.
    assert [s.num_sources for s in report.plan] == [1, 1, 1]
    # The synthesis prompt carried the references under the background heading.
    _plan_call, syn_call = llm.calls
    assert "[背景资料" in syn_call[1]
    assert "śūnyatā 定义" in syn_call[1]


@pytest.mark.anyio
async def test_agent_dedupes_references_by_kind_and_term():
    plan = '{"steps":[{"query":"空","tool":"dictionary"},{"query":"空义","tool":"dictionary"},{"query":"c","tool":"corpus"}]}'
    llm = _ScriptedLLM(plan, "答【《般若经》第1卷】")

    async def corpus(q):
        return [_src(251, "般若经")]

    async def dict_tool(q):
        # Both dictionary steps return the same headword "空" → deduped to one.
        return [ResearchReference(kind="dictionary", term="空", detail="d")]

    report = await ResearchAgent(
        complete=llm, corpus_tool=corpus, dict_tool=dict_tool
    ).run("q", max_steps=6)
    assert len(report.references) == 1


@pytest.mark.anyio
async def test_agent_falls_back_to_corpus_when_ref_tool_unwired():
    # Planner asks for "dictionary" but no dict_tool is injected → corpus used.
    plan = '{"steps":[{"query":"空","tool":"dictionary"}]}'
    llm = _ScriptedLLM(plan, "答【《般若经》第1卷】")
    used = []

    async def corpus(q):
        used.append(q)
        return [_src(251, "般若经")]

    report = await ResearchAgent(complete=llm, corpus_tool=corpus).run("q")
    assert used == ["空"]                    # dictionary step fell back to corpus
    assert report.references == []
    assert len(report.sources) == 1


@pytest.mark.anyio
async def test_references_dont_enable_fabricated_citations():
    # An entity reference names 《楞严经》 but it was NOT retrieved as a corpus
    # source; if the synthesis 【】-cites it, the guard must still strip it.
    plan = '{"steps":[{"query":"楞严","tool":"entity"},{"query":"心经","tool":"corpus"}]}'
    llm = _ScriptedLLM(plan, "如【《楞严经》第5卷】所述。")

    async def corpus(q):
        return [_src(251, "般若波罗蜜多心经")]

    async def entity_tool(q):
        return [ResearchReference(kind="entity", term="楞严经", detail="经典", source="text")]

    report = await ResearchAgent(
        complete=llm, corpus_tool=corpus, entity_tool=entity_tool
    ).run("q")
    assert "【《楞严经》" not in report.answer          # fabricated cite stripped
    assert report.trust_status.state == "citation_corrected"


# ── prompt + grounding units ─────────────────────────────────────────────


def test_synthesis_context_includes_parallels_for_cross_canon():
    from app.services.research_agent import _format_sources_context

    s = _src(2, "中阿含经")
    s.parallel_chunks = [ParallelChunk(
        text_id=272, juan_num=1, chunk_index=0, chunk_text="Right View pali text",
        lang="pi", title="Majjhima 9", urn="fojin:sc/mn9.1",
    )]
    ctx = _format_sources_context([s])
    assert "[出处: 《中阿含经》第1卷]" in ctx
    assert "[跨藏对读]" in ctx
    assert "[巴利]《Majjhima 9》" in ctx


def test_build_plan_prompt_asks_for_json():
    system, user = build_plan_prompt("空性问题")
    assert "JSON" in system
    assert "空性问题" in user


def test_ground_answer_passes_clean_answer_through():
    answer = "《心经》讲空【《心经》第1卷】。"
    out, trust = ground_answer(answer, [_src(251, "心经")])
    assert out == answer
    assert trust.state == "verified"
