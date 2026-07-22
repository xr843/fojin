"""Open-data bulk exports ship off.

`/api/exports/*` is unauthenticated and streams whole datasets with keyset
pagination and no overall cap. Measured against production before gating it:

    GET /api/exports/kg.json        50.7 MB   62.3 s
    GET /api/exports/metadata.csv    0.87 MB   2.8 s

It was also absent from `STRICT_PATHS`, so it inherited the loose 200/min
default — a single IP could hold 200 concurrent 62-second streaming queries
open, which exhausts the connection pool long before bandwidth becomes the
problem. #1016 had just linked it from the main navigation.

The feature itself is intended (versioned, licensed open data); it is simply
not ready to be public, so it now sits behind `ENABLE_OPEN_DATA_EXPORTS`
and the routes are not registered at all when it is off — 404, and absent
from the OpenAPI schema, rather than disabled stubs.
"""

import pytest

from app.config import settings


def test_ships_disabled_by_default():
    assert settings.enable_open_data_exports is False


@pytest.mark.anyio
@pytest.mark.parametrize(
    "path",
    [
        "/api/exports/stats",
        "/api/exports/metadata.csv",
        "/api/exports/kg.json",
        "/api/exports/kg.jsonld",
        "/api/exports/alignments.jsonl",
    ],
)
async def test_routes_are_not_mounted(client, path):
    resp = await client.get(path)
    assert resp.status_code == 404


def test_routes_absent_from_openapi():
    from app.main import app

    assert not [p for p in app.openapi()["paths"] if p.startswith("/api/exports")]
