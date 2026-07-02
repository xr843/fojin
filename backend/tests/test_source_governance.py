"""Tests for source governance audit summaries."""

from types import SimpleNamespace

from app.services.source_governance import build_source_governance_report


def _dist(code: str, primary: bool = False, active: bool = True):
    return SimpleNamespace(code=code, is_primary_ingest=primary, is_active=active)


def _source(
    code: str,
    *,
    active: bool = True,
    health: str = "ok",
    license_spdx: str | None = "CC-BY-4.0",
    license_verified: object | None = object(),
    embedding_allowed: bool | None = True,
    redistribution_allowed: bool | None = True,
    supports_fulltext: bool = False,
    has_local_fulltext: bool = False,
    has_remote_fulltext: bool = False,
    supports_search: bool = False,
    supports_api: bool = False,
    supports_iiif: bool = False,
    distributions: list[object] | None = None,
):
    return SimpleNamespace(
        code=code,
        is_active=active,
        health_status=health,
        license_spdx=license_spdx,
        license_verified_at=license_verified,
        embedding_allowed=embedding_allowed,
        redistribution_allowed=redistribution_allowed,
        supports_fulltext=supports_fulltext,
        has_local_fulltext=has_local_fulltext,
        has_remote_fulltext=has_remote_fulltext,
        supports_search=supports_search,
        supports_api=supports_api,
        supports_iiif=supports_iiif,
        distributions=distributions or [],
    )


def test_governance_report_prioritizes_license_gaps_for_ingested_fulltext_sources():
    sources = [
        _source(
            "cbeta",
            has_local_fulltext=True,
            supports_fulltext=True,
            distributions=[_dist("cbeta-xml", primary=True)],
        ),
        _source(
            "unknown-fulltext",
            has_remote_fulltext=True,
            supports_fulltext=True,
            license_spdx=None,
            license_verified=None,
            embedding_allowed=None,
            distributions=[_dist("unknown-dump", primary=True)],
        ),
        _source("catalog-only", license_spdx=None, license_verified=None),
        _source("dead-site", health="unreachable"),
        _source("inactive-source", active=False, health="unreachable", license_spdx=None),
    ]

    report = build_source_governance_report(sources)

    assert report["total_active"] == 4
    assert report["health_status_counts"] == {"ok": 3, "unreachable": 1}
    assert report["health_review_codes"] == ["dead-site"]
    assert report["license_review_codes"] == ["unknown-fulltext"]
    assert report["catalog_only_codes"] == ["catalog-only"]
    assert report["local_or_remote_fulltext_count"] == 2
    assert report["primary_ingest_count"] == 2
    assert report["missing_license_spdx_count"] == 2
    assert report["missing_license_verified_count"] == 2
    assert report["embedding_unknown_count"] == 1


def test_governance_report_flags_fulltext_without_primary_ingest_distribution():
    sources = [
        _source("sc", supports_fulltext=True, has_remote_fulltext=True),
        _source("iiif-only", supports_iiif=True),
    ]

    report = build_source_governance_report(sources)

    assert report["missing_primary_ingest_codes"] == ["sc"]
    assert report["catalog_only_codes"] == []
