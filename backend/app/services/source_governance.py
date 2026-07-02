"""Source governance audit helpers.

The public /sources catalog mixes catalog pointers, remote search endpoints,
local full-text corpora, and primary ingest feeds. These helpers turn that
metadata into small review queues for health and rights clean-up.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


def _primary_ingest_distributions(source: Any) -> list[Any]:
    return [
        dist
        for dist in getattr(source, "distributions", []) or []
        if getattr(dist, "is_active", False) and getattr(dist, "is_primary_ingest", False)
    ]


def _has_fulltext_surface(source: Any) -> bool:
    return any(
        bool(getattr(source, attr, False))
        for attr in ("supports_fulltext", "has_local_fulltext", "has_remote_fulltext")
    )


def _has_any_product_surface(source: Any) -> bool:
    return any(
        bool(getattr(source, attr, False))
        for attr in (
            "supports_search",
            "supports_fulltext",
            "has_local_fulltext",
            "has_remote_fulltext",
            "supports_api",
            "supports_iiif",
        )
    )


def _needs_license_review(source: Any) -> bool:
    if not (_has_fulltext_surface(source) or _primary_ingest_distributions(source)):
        return False
    return any(
        value is None or value == ""
        for value in (
            getattr(source, "license_spdx", None),
            getattr(source, "license_verified_at", None),
            getattr(source, "embedding_allowed", None),
            getattr(source, "redistribution_allowed", None),
        )
    )


def build_source_governance_report(sources: list[Any]) -> dict[str, Any]:
    """Build a deterministic governance summary for active data sources."""

    active_sources = [source for source in sources if getattr(source, "is_active", False)]
    health_counts = Counter(getattr(source, "health_status", "unknown") or "unknown" for source in active_sources)

    primary_ingest_codes: list[str] = []
    health_review_codes: list[str] = []
    license_review_codes: list[str] = []
    catalog_only_codes: list[str] = []
    missing_primary_ingest_codes: list[str] = []

    for source in active_sources:
        code = getattr(source, "code", "")
        primary_distributions = _primary_ingest_distributions(source)
        if primary_distributions:
            primary_ingest_codes.append(code)
        if (getattr(source, "health_status", "ok") or "ok") != "ok":
            health_review_codes.append(code)
        if _needs_license_review(source):
            license_review_codes.append(code)
        if (
            (getattr(source, "health_status", "ok") or "ok") == "ok"
            and not _has_any_product_surface(source)
            and not primary_distributions
        ):
            catalog_only_codes.append(code)
        if _has_fulltext_surface(source) and not primary_distributions:
            missing_primary_ingest_codes.append(code)

    return {
        "total_active": len(active_sources),
        "health_status_counts": dict(sorted(health_counts.items())),
        "health_review_codes": health_review_codes,
        "license_review_codes": license_review_codes,
        "catalog_only_codes": catalog_only_codes,
        "missing_primary_ingest_codes": missing_primary_ingest_codes,
        "local_or_remote_fulltext_count": sum(1 for source in active_sources if _has_fulltext_surface(source)),
        "primary_ingest_count": len(primary_ingest_codes),
        "primary_ingest_codes": primary_ingest_codes,
        "missing_license_spdx_count": sum(
            1 for source in active_sources if not getattr(source, "license_spdx", None)
        ),
        "missing_license_verified_count": sum(
            1 for source in active_sources if getattr(source, "license_verified_at", None) is None
        ),
        "embedding_unknown_count": sum(
            1 for source in active_sources if getattr(source, "embedding_allowed", None) is None
        ),
        "redistribution_unknown_count": sum(
            1 for source in active_sources if getattr(source, "redistribution_allowed", None) is None
        ),
    }
