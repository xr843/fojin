"""Agentic research assistant — multi-step planned retrieval over the aligned
corpus, then a grounded, citation-verified synthesis.

This is fojin's killer app: instead of one-shot RAG, a question like "how is
śūnyatā treated across Prajñāpāramitā vs Madhyamaka vs Yogācāra, with cited
cross-canon parallels" is *decomposed* into sub-queries, each retrieved
separately (bringing its own Pali/Tibetan parallels + URNs), then synthesized
into one answer whose every citation is checked against what was actually
retrieved. Only fojin's integrated, aligned, URN-addressable corpus makes this
possible — a single-canon tool can't.

Why it's built *after* the verifiability foundation (PRs #896/#897/#898):
multi-hop retrieval amplifies hallucination, so the synthesis is put through the
exact same deterministic guards the chat path uses —
``enforce_citation_whitelist`` (strip un-retrieved citations),
``verify_quoted_content`` (flag invented quotes), ``build_trust_status`` — and
the report carries that trust verdict. The agent can plan, but it cannot cite
what it didn't retrieve.

Design for testability: the LLM call (``complete``) and each retrieval tool are
injected callables, so the plan → retrieve → synthesize orchestration is
unit-tested with fakes — no live LLM or DB. ``build_research_agent`` wires the
production bindings.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from app.schemas.chat import ChatSource, ChatTrustStatus
from app.schemas.research import ResearchReference, ResearchReport, ResearchStep
from app.services.chat_trust import build_trust_status
from app.services.citation_guard import enforce_citation_whitelist
from app.services.quote_verifier import verify_quoted_content

logger = logging.getLogger(__name__)

# Type of an injected LLM text completion: (system, user) -> assistant text.
CompleteFn = Callable[[str, str], Awaitable[str]]
# A corpus retrieval tool: query -> citation-graded sources (each with a URN).
RetrieveFn = Callable[[str], Awaitable[list[ChatSource]]]
# A reference tool (dictionary/entity): query -> supplementary background hits.
ReferenceFn = Callable[[str], Awaitable[list[ResearchReference]]]

# The tools a plan step may dispatch to. Unknown tool names coerce to "corpus".
_KNOWN_TOOLS = ("corpus", "dictionary", "entity")

# Absolute ceilings independent of the request's max_steps — defence in depth
# against a planner that emits a pathological plan.
_HARD_MAX_STEPS = 6
_MAX_SOURCES = 24
_MAX_REFERENCES = 20
_MAX_QUERY_LEN = 200


@dataclass
class PlanStep:
    tool: str
    query: str
    aspect: str = ""


@dataclass
class _Collected:
    """Accumulator for sources gathered across steps, deduped by (text_id,
    juan_num) so the same fascicle retrieved by two sub-queries counts once."""
    sources: list[ChatSource] = field(default_factory=list)
    _seen: set[tuple[int, int]] = field(default_factory=set)

    def add(self, srcs: list[ChatSource]) -> int:
        added = 0
        for s in srcs:
            if len(self.sources) >= _MAX_SOURCES:
                break
            key = (s.text_id, s.juan_num)
            if s.text_id and s.text_id > 0 and key in self._seen:
                continue
            self._seen.add(key)
            self.sources.append(s)
            added += 1
        return added


@dataclass
class _CollectedRefs:
    """Accumulator for dictionary/entity references, deduped by (kind, term)."""
    refs: list[ResearchReference] = field(default_factory=list)
    _seen: set[tuple[str, str]] = field(default_factory=set)

    def add(self, items: list[ResearchReference]) -> int:
        added = 0
        for r in items:
            if len(self.refs) >= _MAX_REFERENCES:
                break
            key = (r.kind, r.term)
            if key in self._seen:
                continue
            self._seen.add(key)
            self.refs.append(r)
            added += 1
        return added


def build_plan_prompt(question: str) -> tuple[str, str]:
    """(system, user) prompts that ask the LLM to decompose a research question
    into 2–5 focused sub-queries, each tagged with the tool to run, as JSON."""
    system = (
        "你是佛教文献研究的检索规划器。把用户的研究问题拆解成 2-5 个聚焦的检索步骤，"
        "每步针对问题的一个方面，并选择合适的工具：\n"
        "- \"corpus\"：在佛典语料库中语义检索经文段落（默认，用于义理/经文内容，"
        "会自动带出跨藏对读）。\n"
        "- \"dictionary\"：查佛学辞典，解释某个术语/名相的定义。\n"
        "- \"entity\"：查知识图谱，获取某个人物/经典/宗派/地点的背景事实。\n"
        "只输出 JSON，格式："
        "{\"steps\":[{\"tool\":\"corpus\",\"query\":\"...\",\"aspect\":\"...\"}]}。"
        "query 是关键词式子查询（辞典/实体步骤填要查的术语或名称）；"
        "aspect 是该步考察的方面（简短中文）。多数步骤应为 corpus。"
        "不要输出 JSON 以外的任何文字。"
    )
    return system, f"研究问题：{question}"


def parse_plan(text: str, question: str, max_steps: int) -> list[PlanStep]:
    """Parse the planner's JSON into capped PlanSteps.

    Robust to fenced code blocks and trailing prose. On any parse failure or an
    empty plan, falls back to a single corpus step on the original question — a
    degraded plan still produces a grounded answer, which beats erroring out.
    """
    steps: list[PlanStep] = []
    obj = _extract_json_object(text)
    if isinstance(obj, dict):
        raw_steps = obj.get("steps")
        if isinstance(raw_steps, list):
            for item in raw_steps:
                if not isinstance(item, dict):
                    continue
                query = str(item.get("query", "")).strip()[:_MAX_QUERY_LEN]
                if not query:
                    continue
                aspect = str(item.get("aspect", "")).strip()[:80]
                # tool defaults to corpus; a hallucinated/unknown tool name
                # coerces to corpus so a step is never dropped.
                tool = str(item.get("tool", "corpus")).strip() or "corpus"
                if tool not in _KNOWN_TOOLS:
                    tool = "corpus"
                steps.append(PlanStep(tool=tool, query=query, aspect=aspect))

    cap = max(1, min(max_steps, _HARD_MAX_STEPS))
    steps = steps[:cap]
    if not steps:
        steps = [PlanStep(tool="corpus", query=question.strip()[:_MAX_QUERY_LEN], aspect="")]
    return steps


def _extract_json_object(text: str) -> object:
    """Best-effort extraction of the first top-level JSON object from LLM text
    (which may wrap it in ```json fences or add commentary)."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start = text.find("{")
        end = text.rfind("}")
        candidate = text[start : end + 1] if start != -1 and end > start else None
    if not candidate:
        return None
    try:
        return json.loads(candidate)
    except (ValueError, TypeError):
        return None


def build_synthesis_prompt(
    question: str,
    sources: list[ChatSource],
    references: list[ResearchReference] | None = None,
) -> tuple[str, str]:
    """(system, user) prompts for the grounded synthesis over collected sources.

    Reuses the chat path's citation contract verbatim — the ``[出处: 《X》第N卷]``
    context labels and the ``【《X》第N卷】`` clickable-citation rule — so the same
    citation_guard / quote_verifier that protect chat also protect this answer.
    Dictionary/entity ``references`` are given as background under a distinct
    heading and are explicitly NOT citable with 【】, keeping the clickable
    citation strictly to corpus passages.
    """
    system = (
        "你是佛教文献研究助手。以下是系统自动检索到的佛典片段与可选的辞典/知识图谱背景资料"
        "（由系统检索得到，**不是用户手动提供的**，所以不要说「您提供的资料」之类）。\n"
        "请综合这些材料写一篇结构化的研究性回答，比较不同经典/宗派/传承对该问题的处理。\n"
        "**引用规则（严格）**：\n"
        "- 只能引用下方 `[出处: 《经名》第N卷]` 标明的经典，格式写作【《经名》第N卷】，"
        "使用出处行里的原始经名与真实卷号，不要改写或杜撰。\n"
        "- 严禁把检索片段之外的经典写成【...】引用；那样会生成打不开的链接，严重伤害可信度。"
        "宁可用散文提及「《X》中说……」。\n"
        "- **`[背景资料]` 里的辞典/知识图谱条目仅供理解术语与人物，不是经文出处，"
        "绝不可写成【...】引用**，只能用散文融入。\n"
        "- **直接引号（「」\"\"）内的文字必须逐字来自检索片段，一字不改**；转述、概括、"
        "用现代语解释一律用散文，不要给转述文字加引号冒充原文（学者会据此逐字核对）。\n"
        "- 若检索片段含跨藏对读（parallel_chunks / 巴利·藏），可对比不同传承的表述。\n"
        "- 检索不足以支撑的部分，如实说明，不要编造。"
    )
    context = _format_sources_context(sources)
    user = f"研究问题：{question}\n\n检索到的片段：\n{context}"
    ref_block = _format_references_context(references or [])
    if ref_block:
        user += f"\n\n[背景资料（辞典/知识图谱，不可用【】引用）]：\n{ref_block}"
    return system, user


def _format_references_context(references: list[ResearchReference]) -> str:
    """Render dictionary/entity references into a background block, clearly
    separate from the citable `[出处: …]` corpus context."""
    lines: list[str] = []
    for r in references:
        kind = {"dictionary": "辞典", "entity": "知识图谱"}.get(r.kind, r.kind)
        src = f"（{r.source}）" if r.source else ""
        lines.append(f"- [{kind}] {r.term}{src}: {r.detail}")
    return "\n".join(lines)


def _format_sources_context(sources: list[ChatSource]) -> str:
    """Render collected sources into the `[出处: …]` context block the citation
    guard understands, including any cross-canon parallels."""
    blocks: list[str] = []
    for s in sources:
        if s.text_id <= 0:
            continue
        label = f"《{s.title_zh}》第{s.juan_num}卷" if s.title_zh else f"text#{s.text_id} 第{s.juan_num}卷"
        head = f"[出处: {label}]"
        body = s.chunk_text or ""
        parallels = s.parallel_chunks or []
        if parallels:
            plines = []
            for p in parallels[:3]:
                lang = {"pi": "巴利", "bo": "藏", "sa": "梵", "en": "英", "lzh": "汉"}.get(p.lang, p.lang)
                title = p.title or "其他藏经"
                plines.append(f"  · [{lang}]《{title}》第{p.juan_num}卷: {p.chunk_text[:200]}")
            body += "\n[跨藏对读]\n" + "\n".join(plines)
        blocks.append(f"{head}\n{body}")
    return "\n\n".join(blocks) if blocks else "（未检索到相关片段）"


class ResearchAgent:
    """Plan → retrieve → synthesize, over injected LLM + tools.

    ``corpus_tool`` is required (citation-graded passages); ``dict_tool`` and
    ``entity_tool`` are optional reference tools. A plan step whose tool has no
    binding falls back to the corpus tool, so the agent degrades to corpus-only
    when references aren't wired.
    """

    def __init__(
        self,
        complete: CompleteFn,
        corpus_tool: RetrieveFn,
        *,
        dict_tool: ReferenceFn | None = None,
        entity_tool: ReferenceFn | None = None,
    ) -> None:
        self._complete = complete
        self._corpus_tool = corpus_tool
        self._ref_tools: dict[str, ReferenceFn] = {}
        if dict_tool is not None:
            self._ref_tools["dictionary"] = dict_tool
        if entity_tool is not None:
            self._ref_tools["entity"] = entity_tool

    async def run(self, question: str, max_steps: int = 4) -> ResearchReport:
        question = question.strip()

        # 1. Plan (LLM). A planner failure degrades to a single-step plan.
        try:
            plan_sys, plan_user = build_plan_prompt(question)
            plan_text = await self._complete(plan_sys, plan_user)
        except Exception:
            logger.warning("research planner LLM call failed; using single-step plan", exc_info=True)
            plan_text = ""
        plan = parse_plan(plan_text, question, max_steps)

        # 2. Dispatch each step: corpus → citation-graded sources; dictionary /
        #    entity → supplementary references. Both collected + deduped across
        #    steps. A failing step contributes nothing but doesn't sink the run.
        collected = _Collected()
        refs = _CollectedRefs()
        run_steps: list[ResearchStep] = []
        for step in plan:
            ref_tool = self._ref_tools.get(step.tool)
            try:
                if ref_tool is not None:
                    added = refs.add(await ref_tool(step.query))
                else:
                    added = collected.add(await self._corpus_tool(step.query))
            except Exception:
                logger.warning("research step failed (%s %r)", step.tool, step.query, exc_info=True)
                added = 0
            run_steps.append(
                ResearchStep(tool=step.tool, query=step.query, aspect=step.aspect, num_sources=added)
            )

        sources = collected.sources
        references = refs.refs

        # 3. Synthesize (LLM), then ground the answer with the same guards the
        #    chat path uses. No corpus sources → don't fabricate a cited answer;
        #    return an honest note (references alone can't ground 【】 citations).
        if not sources:
            return ResearchReport(
                question=question,
                plan=run_steps,
                answer="未能检索到与该研究问题相关的佛典片段，无法给出有据可依的回答。",
                sources=[],
                references=references,
                trust_status=build_trust_status("", [], citation_mutations=[], quote_mutations=[]),
            )

        syn_sys, syn_user = build_synthesis_prompt(question, sources, references)
        try:
            answer = await self._complete(syn_sys, syn_user)
        except Exception:
            logger.warning("research synthesis LLM call failed", exc_info=True)
            answer = "抱歉，综合分析阶段的 AI 服务暂时不可用，请稍后重试。"

        answer, trust = ground_answer(answer, sources)
        return ResearchReport(
            question=question, plan=run_steps, answer=answer, sources=sources,
            references=references, trust_status=trust,
        )


def ground_answer(answer: str, sources: list[ChatSource]) -> tuple[str, ChatTrustStatus]:
    """Run the synthesis through the deterministic citation guards and return the
    corrected answer + its trust status — the same machinery as the chat path,
    so a multi-step answer is held to the same "每一句点回原典" bar."""
    corrected, cite_muts = enforce_citation_whitelist(answer, sources)
    corrected, quote_muts = verify_quoted_content(corrected, sources)
    trust = build_trust_status(
        corrected, sources, citation_mutations=cite_muts, quote_mutations=quote_muts
    )
    return corrected, trust


# ── production wiring ────────────────────────────────────────────────────

# Per-step retrieval breadth. Kept modest — the agent runs several steps and
# dedupes, so a wide per-step fetch mostly adds redundant context + tokens.
_STEP_PGVECTOR_LIMIT = 8
_SYNTHESIS_MAX_TOKENS = 2600
_PLAN_MAX_TOKENS = 400
# Reference (dictionary/entity) lookups are background, so keep them small.
_REF_LOOKUP_LIMIT = 5
_REF_DETAIL_CHARS = 400


def build_research_agent(db: object, user: object | None) -> ResearchAgent:
    """Wire a ResearchAgent to the real corpus retriever + the platform/BYOK LLM.

    Imports the heavy retrieval + LLM deps lazily so importing this module (e.g.
    for unit tests of the pure orchestration) stays cheap and DB-free.
    """
    import httpx

    from app.core.url_security import create_pinned_https_transport
    from app.services.llm_client import _resolve_llm_config
    from app.services.rag_retrieval import retrieve_rag_context

    api_url, api_key, model, _is_byok, provider = _resolve_llm_config(user)  # type: ignore[arg-type]

    async def complete(system: str, user_msg: str) -> str:
        # OpenAI-compatible chat/completions — the same call shape eval/run_eval
        # uses in prod. max_tokens differs per call site (plan vs synthesis) but
        # the planner prompt is short, so one modest ceiling covers both.
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user_msg}]
        # For BYOK "custom" endpoints, pin the outbound connection to a
        # validated public IP (runtime DNS check + rebinding-proof transport) —
        # the same guard the chat path applies. Platform/known providers use
        # fixed, trusted base URLs, so they need no per-request pinning.
        transport = (
            await create_pinned_https_transport(api_url, label="自定义 API 地址")
            if provider == "custom"
            else None
        )
        async with httpx.AsyncClient(timeout=60, transport=transport) as client:
            resp = await client.post(
                f"{api_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0.5,
                    "max_tokens": _SYNTHESIS_MAX_TOKENS,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"] or ""

    async def corpus_tool(query: str) -> list[ChatSource]:
        sources, _context = await retrieve_rag_context(
            db, query, pgvector_limit=_STEP_PGVECTOR_LIMIT  # type: ignore[arg-type]
        )
        return sources

    async def dict_tool(query: str) -> list[ResearchReference]:
        # Reuse the dictionary endpoint's 简繁-aware headword matching helpers so
        # the agent's lookups behave like the site's dictionary search.
        from sqlalchemy import select
        from sqlalchemy.orm import joinedload

        from app.api.dictionary import _build_exact_prefix_conditions, _zh_variants
        from app.models.dictionary import DictionaryEntry

        variants = _zh_variants(query)
        stmt = (
            select(DictionaryEntry)
            .where(_build_exact_prefix_conditions(variants))
            .options(joinedload(DictionaryEntry.source))
            .limit(_REF_LOOKUP_LIMIT)
        )
        rows = (await db.execute(stmt)).unique().scalars().all()  # type: ignore[union-attr]
        return [
            ResearchReference(
                kind="dictionary",
                term=e.headword,
                detail=(e.definition or "")[:_REF_DETAIL_CHARS],
                source=(e.source.name_zh if e.source else None),
            )
            for e in rows
        ]

    async def entity_tool(query: str) -> list[ResearchReference]:
        from app.services.knowledge_graph import search_entities

        entities, _total = await search_entities(
            db, query, None, _REF_LOOKUP_LIMIT, 0  # type: ignore[arg-type]
        )
        return [
            ResearchReference(
                kind="entity",
                term=e.name_zh,
                detail=(getattr(e, "description", "") or "")[:_REF_DETAIL_CHARS],
                source=getattr(e, "entity_type", None),
            )
            for e in entities
        ]

    return ResearchAgent(
        complete=complete, corpus_tool=corpus_tool,
        dict_tool=dict_tool, entity_tool=entity_tool,
    )
