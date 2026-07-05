"""Agentic research assistant endpoint.

POST /api/research/query decomposes a scholarly question into sub-queries,
retrieves grounded sources for each (with cross-canon parallels + URNs), and
returns one citation-verified synthesis. It is additive — separate from the
chat / SSE path — and authenticated, because a single request fans out into
several LLM + retrieval calls and so must be bounded to signed-in users.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.research import ResearchReport, ResearchRequest
from app.services.research_agent import build_research_agent

router = APIRouter(prefix="/research", tags=["research"])


@router.post("/query", response_model=ResearchReport)
async def research_query(
    request: ResearchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ResearchReport:
    """Run the multi-step research agent for one question.

    Returns the plan (how the question was decomposed), the deduplicated cited
    sources (each with a URN), the synthesized answer, and the deterministic
    trust status of that answer.
    """
    agent = build_research_agent(db, user)
    return await agent.run(request.question, max_steps=request.max_steps)
