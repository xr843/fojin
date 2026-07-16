"""Compact trust status and persistence for chat answers."""

import re
from collections.abc import Iterable
from dataclasses import asdict, is_dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatAnswerDiagnostic
from app.schemas.chat import ChatSource, ChatTrustStatus
from app.services.quote_verifier import count_checked_quotes

_CITATION_RE = re.compile(r"【《[^》]+》(?:第[^】]+?卷)?】")


def _valid_sources(sources: Iterable[ChatSource]) -> list[ChatSource]:
    return [s for s in sources if s.text_id > 0]


def _score_bounds(sources: list[ChatSource]) -> tuple[float | None, float | None]:
    scores = [float(s.score) for s in sources if s.score is not None]
    if not scores:
        return None, None
    return round(max(scores), 3), round(min(scores), 3)


def build_trust_status(
    answer: str,
    sources: list[ChatSource],
    *,
    citation_mutations: list[Any],
    quote_mutations: list[Any],
) -> ChatTrustStatus:
    """Summarise citation/source diagnostics into a frontend-safe status."""
    valid_sources = _valid_sources(sources)
    citation_count = len(_CITATION_RE.findall(answer or ""))
    max_score, min_score = _score_bounds(valid_sources)

    if not valid_sources:
        state = "no_sources"
    elif quote_mutations:
        # verify_quoted_content now *downgrades* a non-verbatim quote to prose,
        # so a quote mutation means "we relaxed a paraphrase-as-quote" — the
        # served answer is honest. This is a correction tier (like
        # citation_corrected), not the old "unverified" warning.
        state = "quote_relaxed"
    elif citation_mutations:
        state = "citation_corrected"
    elif citation_count:
        state = "verified"
    else:
        state = "sources_available"

    return ChatTrustStatus(
        state=state,
        citation_count=citation_count,
        source_count=len(valid_sources),
        citation_mutation_count=len(citation_mutations),
        quote_mutation_count=len(quote_mutations),
        quote_checked_count=count_checked_quotes(answer or "", valid_sources),
        max_source_score=max_score,
        min_source_score=min_score,
    )


def _serialize_mutations(mutations: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for mutation in mutations:
        if is_dataclass(mutation):
            out.append(asdict(mutation))
        elif hasattr(mutation, "model_dump"):
            out.append(mutation.model_dump())
        elif isinstance(mutation, dict):
            out.append(dict(mutation))
        else:
            out.append(dict(getattr(mutation, "__dict__", {})))
    return out


def trust_status_from_diagnostic(
    diagnostic: ChatAnswerDiagnostic | None,
) -> ChatTrustStatus | None:
    if diagnostic is None:
        return None
    return ChatTrustStatus(
        state=diagnostic.trust_state,  # type: ignore[arg-type]
        citation_count=diagnostic.citation_count,
        source_count=diagnostic.source_count,
        citation_mutation_count=diagnostic.citation_mutation_count,
        quote_mutation_count=diagnostic.quote_mutation_count,
        max_source_score=diagnostic.max_source_score,
        min_source_score=diagnostic.min_source_score,
    )


async def persist_answer_diagnostic(
    db: AsyncSession,
    *,
    message_id: int,
    trust_status: ChatTrustStatus,
    citation_mutations: list[Any],
    quote_mutations: list[Any],
) -> ChatAnswerDiagnostic:
    """Insert or update the diagnostic row for one assistant message."""
    result = await db.execute(
        select(ChatAnswerDiagnostic).where(ChatAnswerDiagnostic.message_id == message_id)
    )
    row = result.scalar_one_or_none()

    values = {
        "trust_state": trust_status.state,
        "citation_count": trust_status.citation_count,
        "source_count": trust_status.source_count,
        "citation_mutation_count": trust_status.citation_mutation_count,
        "quote_mutation_count": trust_status.quote_mutation_count,
        "max_source_score": trust_status.max_source_score,
        "min_source_score": trust_status.min_source_score,
        "citation_mutations": _serialize_mutations(citation_mutations),
        "quote_mutations": _serialize_mutations(quote_mutations),
    }

    if row is None:
        row = ChatAnswerDiagnostic(message_id=message_id, **values)
        db.add(row)
    else:
        for key, value in values.items():
            setattr(row, key, value)

    await db.commit()
    await db.refresh(row)
    return row
