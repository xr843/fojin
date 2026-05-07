"""Tests for the provenance helper.

The helper is the choke point every ingestion script will route through,
so the rejection paths matter as much as the happy path: a typo in
``tier`` at any ingestion site must surface as a hard error, not as a
quietly mis-tagged row that pollutes audit queries forever.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.models.knowledge_graph import KGEntity
from app.services.provenance import (
    SOURCE_TIER_AUTHORITATIVE,
    SOURCE_TIER_INFERRED,
    VALID_SOURCE_TIERS,
    apply_provenance,
)


def _bare_entity() -> KGEntity:
    return KGEntity(entity_type="person", name_zh="测试")


def test_apply_provenance_sets_all_three_fields_with_default_timestamp():
    e = _bare_entity()
    before = datetime.now(UTC)
    apply_provenance(e, tier=SOURCE_TIER_AUTHORITATIVE, source_version="dila-2025q1")
    after = datetime.now(UTC)

    assert e.source_tier == SOURCE_TIER_AUTHORITATIVE
    assert e.source_version == "dila-2025q1"
    assert e.ingested_at is not None
    assert before <= e.ingested_at <= after


def test_apply_provenance_accepts_explicit_ingested_at_for_backfill():
    """Backfill scripts must be able to set ``ingested_at`` to the
    snapshot's date, not the moment the script happened to run."""
    e = _bare_entity()
    snapshot_date = datetime(2024, 6, 1, tzinfo=UTC)
    apply_provenance(
        e,
        tier=SOURCE_TIER_INFERRED,
        source_version="deepseek-chat-2024-06",
        ingested_at=snapshot_date,
    )
    assert e.ingested_at == snapshot_date


def test_apply_provenance_rejects_unknown_tier():
    e = _bare_entity()
    with pytest.raises(ValueError, match="unknown source_tier"):
        apply_provenance(e, tier="trustworthy", source_version="x-2025")
    # Entity must remain untouched on error so a caller cannot half-tag
    # a row by passing a typo.
    assert e.source_tier is None
    assert e.source_version is None
    assert e.ingested_at is None


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_apply_provenance_rejects_blank_source_version(blank: str):
    e = _bare_entity()
    with pytest.raises(ValueError, match="source_version"):
        apply_provenance(e, tier=SOURCE_TIER_AUTHORITATIVE, source_version=blank)


def test_valid_tiers_constant_is_immutable_and_complete():
    """Lock in the four tiers we ship with. Adding a new tier should be
    a deliberate code change that fails this test until updated."""
    assert isinstance(VALID_SOURCE_TIERS, frozenset)
    assert {
        "authoritative",
        "curated",
        "derived",
        "inferred",
    } == VALID_SOURCE_TIERS


def test_apply_provenance_returns_same_entity_for_chaining():
    e = _bare_entity()
    result = apply_provenance(e, tier="curated", source_version="wikipedia-2026-05")
    assert result is e


def test_default_ingested_at_is_utc_aware():
    """A naive datetime would break comparisons against the
    timezone-aware columns the migration created."""
    e = _bare_entity()
    apply_provenance(e, tier="derived", source_version="amap-v3-2026")
    assert e.ingested_at.tzinfo is not None
    # Should be very recent — guard against a pathological default.
    assert datetime.now(UTC) - e.ingested_at < timedelta(seconds=5)
