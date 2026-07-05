"""Schemas for the agentic research assistant (POST /api/research/query).

The research agent decomposes a scholarly question into sub-queries, retrieves
grounded sources for each (with cross-canon parallels + portable URNs), then
synthesizes a single cited answer. These types are the request/response
contract; the orchestration lives in app.services.research_agent.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.chat import ChatSource, ChatTrustStatus

# The agent's tool vocabulary. v1 dispatches "corpus" (semantic retrieval over
# the aligned canon, which brings cross-canon parallels along); the field exists
# so dictionary/entity dispatch is a non-breaking addition.
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


class ResearchReport(BaseModel):
    question: str
    # The agent's decomposition (post-parse, post-cap) — surfaced so the user
    # sees how the question was investigated, not just the final answer.
    plan: list[ResearchStep]
    answer: str
    # De-duplicated sources across all steps; each carries a URN (from #897).
    sources: list[ChatSource]
    # Deterministic grounding verdict for the synthesized answer, from the same
    # citation-guard / quote-verifier pipeline the chat path uses.
    trust_status: ChatTrustStatus | None = None
