"""Provenance tagging for kg_entities (and any other table that adopts
the same triple — source_tier / source_version / ingested_at).

Every ingestion path that creates or refreshes a ``KGEntity`` row should
funnel through ``apply_provenance`` so that the trust band, snapshot
identifier, and ingestion timestamp are set in one place. This is what
makes "show me everything DeepSeek inferred this week" or "rebuild every
row that's older than wikidata-2026Q1" a one-line query instead of an
archaeology project.

Tier semantics (kept short on purpose — VARCHAR not ENUM, so new tiers
land here without a migration):

- ``authoritative`` — primary canonical sources whose authority is the
  reason the project exists at all: DILA, CBETA, Taishō catalogues.
- ``curated`` — community-maintained references with editorial review:
  Wikipedia, Wikidata curated items.
- ``derived``     — automated scrapers against third-party APIs whose
  shape we do not control: Amap, OSM, BDRC.
- ``inferred``    — LLM-assisted extraction. Highest variance; the UI
  should mark these distinctly.
"""

from datetime import UTC, datetime

from app.models.knowledge_graph import KGEntity

SOURCE_TIER_AUTHORITATIVE = "authoritative"
SOURCE_TIER_CURATED = "curated"
SOURCE_TIER_DERIVED = "derived"
SOURCE_TIER_INFERRED = "inferred"

VALID_SOURCE_TIERS: frozenset[str] = frozenset(
    {
        SOURCE_TIER_AUTHORITATIVE,
        SOURCE_TIER_CURATED,
        SOURCE_TIER_DERIVED,
        SOURCE_TIER_INFERRED,
    }
)


def apply_provenance(
    entity: KGEntity,
    *,
    tier: str,
    source_version: str,
    ingested_at: datetime | None = None,
) -> KGEntity:
    """Stamp a ``KGEntity`` with provenance metadata.

    ``tier`` must be one of :data:`VALID_SOURCE_TIERS`; an unknown tier
    is rejected loudly so a typo at an ingestion site does not silently
    create an unfilterable record.

    ``source_version`` is required (never blank) — a row tagged with no
    snapshot identifier is indistinguishable from a legacy un-tagged row
    and defeats the purpose of the column. Use a stable string like
    ``'cbeta-2025q1'`` or ``'wikidata-dump-20260301'``.

    ``ingested_at`` defaults to ``datetime.now(UTC)``; pass an explicit
    value when backfilling so the timestamp reflects the underlying
    snapshot, not the moment the script ran.
    """
    if tier not in VALID_SOURCE_TIERS:
        raise ValueError(
            f"unknown source_tier {tier!r}; expected one of {sorted(VALID_SOURCE_TIERS)}"
        )
    if not source_version or not source_version.strip():
        raise ValueError("source_version must be a non-empty identifier")

    entity.source_tier = tier
    entity.source_version = source_version
    entity.ingested_at = ingested_at or datetime.now(UTC)
    return entity
