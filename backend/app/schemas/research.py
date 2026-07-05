"""Schemas for the agentic research assistant (POST /api/research/query).

The research agent decomposes a scholarly question into sub-queries, retrieves
grounded sources for each (with cross-canon parallels + portable URNs), then
synthesizes a single cited answer. These types are the request/response
contract; the orchestration lives in app.services.research_agent.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.chat import ChatSource, ChatTrustStatus

# The agent's tool vocabulary: "corpus" (semantic retrieval over the aligned
# canon, brings cross-canon parallels along), "dictionary" (term definitions),
# "entity" (knowledge-graph facts). corpus sources are citation-graded;
# dictionary/entity results are supplementary background (see ResearchReference).
ResearchTool = str


class ResearchRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=500)
    # Hard cap on planned retrieval steps — bounds LLM+DB cost per request.
    max_steps: int = Field(default=4, ge=1, le=6)


class ResearchStep(BaseModel):
    """One planned retrieval step: a sub-query the agent ran and how it did."""
    tool: ResearchTool = "corpus"
    query: str
    # Short label for what facet of the question this step investigates.
    aspect: str = ""
    num_sources: int = 0


class ResearchReference(BaseModel):
    """A supplementary background hit from the dictionary or knowledge graph.

    Unlike a corpus ``ChatSource``, a reference is NOT citation-graded (it has no
    《经名》第N卷 form), so it can't be used in a 【】 clickable citation and does
    not affect the answer's trust status — it grounds definitions and entity
    facts as background, keeping the "点回原典" contract strictly to corpus
    passages."""
    kind: str  # 'dictionary' | 'entity'
    term: str
    detail: str = ""
    source: str | None = None


class ResearchReport(BaseModel):
    question: str
    # The agent's decomposition (post-parse, post-cap) — surfaced so the user
    # sees how the question was investigated, not just the final answer.
    plan: list[ResearchStep]
    answer: str
    # De-duplicated sources across all steps; each carries a URN (from #897).
    sources: list[ChatSource]
    # Supplementary dictionary / knowledge-graph background (non-citable).
    references: list[ResearchReference] = []
    # Deterministic grounding verdict for the synthesized answer, from the same
    # citation-guard / quote-verifier pipeline the chat path uses.
    trust_status: ChatTrustStatus | None = None
