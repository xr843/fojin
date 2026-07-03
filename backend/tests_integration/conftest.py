"""Fixtures for real-Elasticsearch integration tests.

Unlike tests/conftest.py, this conftest does NOT mock Elasticsearch.
These tests talk to a live ES server (the repo's own elasticsearch/Dockerfile
image: 8.13.4 + analysis-icu) and exist to catch what the mocked unit suite
cannot: client/server version mismatches, missing ICU plugin, invalid
analyzer/mapping definitions, and query DSL the real server rejects.

They are intentionally NOT collected by the default `pytest tests/` run
(pytest.ini testpaths = tests). Run them explicitly:

    ES_HOST=http://localhost:9200 python -m pytest -q tests_integration/

Hermetic by construction: tests create their own uniquely-named indices
(it_* prefix) and delete them in teardown, so pointing ES_HOST at a dev
cluster will not touch the real buddhist_texts / text_contents indices.
"""

import json
import urllib.error
import urllib.request

import pytest

from app.config import settings
from app.core.elasticsearch import (
    CONTENT_INDEX_SETTINGS,
    INDEX_SETTINGS,
    close_es,
    init_es,
)

# Dedicated test index names so we never touch real data on a shared cluster.
TEST_INDEX = "it_buddhist_texts"
TEST_CONTENT_INDEX = "it_text_contents"


@pytest.fixture(scope="session", autouse=True)
def _require_live_es():
    """Fail loudly (do not skip) when ES is unreachable.

    This lane is opt-in; if it runs at all, a missing server is an
    infrastructure failure that must be visible, not a silent skip.
    """
    url = settings.es_host.rstrip("/") + "/"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:  # nosec B310
            json.loads(resp.read())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        pytest.exit(
            f"Integration tests require a live Elasticsearch at {settings.es_host} "
            f"(set ES_HOST to override): {exc!r}. "
            "Start one with: docker build -t fojin-es elasticsearch/ && "
            "docker run -d -p 9200:9200 -e discovery.type=single-node "
            '-e xpack.security.enabled=false -e "ES_JAVA_OPTS=-Xms512m -Xmx512m" fojin-es',
            returncode=1,
        )


@pytest.fixture
async def es():
    """Real AsyncElasticsearch client via the app's own init path.

    Uses init_es()/close_es() so the exact client construction the FastAPI
    lifespan performs (app/main.py) is what gets exercised.
    """
    client = await init_es()
    yield client
    await close_es()


@pytest.fixture
async def search_indices(es, monkeypatch):
    """Create both app indices (real mappings/analyzers) under test names.

    Monkeypatches the module-level index names bound inside
    app.services.search so the service functions run against the test
    indices. Index creation itself is the first real assertion: it fails
    on any server that lacks the analysis-icu plugin (icu_transform).
    """
    monkeypatch.setattr("app.services.search.INDEX_NAME", TEST_INDEX)
    monkeypatch.setattr("app.services.search.CONTENT_INDEX_NAME", TEST_CONTENT_INDEX)

    await es.indices.delete(
        index=[TEST_INDEX, TEST_CONTENT_INDEX], ignore_unavailable=True
    )
    await es.indices.create(index=TEST_INDEX, body=INDEX_SETTINGS)
    await es.indices.create(index=TEST_CONTENT_INDEX, body=CONTENT_INDEX_SETTINGS)
    try:
        yield es
    finally:
        await es.indices.delete(
            index=[TEST_INDEX, TEST_CONTENT_INDEX], ignore_unavailable=True
        )
