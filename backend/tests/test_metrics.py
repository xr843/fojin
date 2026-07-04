"""Tests for the Prometheus observability wiring (app.core.metrics).

Runs without external services: the exposure test uses the real
``app.main:app`` (already instrumented at import — production path), and
the rest exercise the custom metric objects directly. No second
Instrumentator is created, so the global registry is never double-registered.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import metrics


def _hist_count(hist) -> float:
    """Return the current observation count of a label-less Histogram."""
    for metric in hist.collect():
        for sample in metric.samples:
            if sample.name.endswith("_count"):
                return sample.value
    return 0.0


def test_metrics_endpoint_exposed_on_real_app():
    from app.main import app

    client = TestClient(app)
    # Exercise an instrumented, DB-free route so HTTP metrics have samples.
    # /openapi.json is a Starlette built-in: scope carries endpoint but no
    # route — the fixed path itself must be recorded.
    client.get("/openapi.json")

    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]

    body = resp.text
    # HTTP metrics recorded by MetricsMiddleware, keyed by route template.
    assert "fojin_http_requests_total" in body
    assert "fojin_http_request_duration_seconds" in body
    assert 'handler="/openapi.json"' in body
    # Custom application metrics (registered at import, always emitted).
    assert "fojin_rag_retrieval_seconds" in body
    assert "fojin_rag_context_chunks" in body


def test_metrics_skips_unmatched_and_excluded_paths():
    from app.main import app

    client = TestClient(app)
    client.get("/definitely/not/a/route-xyzzy")   # 404, no route matched
    client.get("/api/version")                     # excluded probe endpoint

    body = client.get("/metrics").text
    assert "route-xyzzy" not in body
    assert 'handler="/api/version"' not in body


def test_handler_label_templates_path_params():
    # Full-prefix template: /api/texts/42 with tid=42 → /api/texts/{tid}.
    # Uses scope["path"], not route.path, which FastAPI 0.139 reports
    # prefix-stripped (see _handler_label docstring).
    route = object()  # only checked for not-None
    assert metrics._handler_label(
        {"route": route, "path": "/api/texts/42", "path_params": {"tid": 42}}
    ) == "/api/texts/{tid}"

    # No params: path is already the template.
    assert metrics._handler_label(
        {"route": route, "path": "/api/search", "path_params": {}}
    ) == "/api/search"

    # Param value repeated as a static segment: only one boundary-anchored
    # replacement happens, longest value first.
    assert metrics._handler_label(
        {"route": route, "path": "/dict/entry/entry-1",
         "path_params": {"slug": "entry-1"}}
    ) == "/dict/entry/{slug}"

    # {x:path} converter — value contains slashes (SEO dict headwords).
    assert metrics._handler_label(
        {"route": route, "path": "/dict/a/b/c",
         "path_params": {"headword": "a/b/c"}}
    ) == "/dict/{headword}"

    # Starlette built-in: endpoint set, route None → fixed path kept.
    assert metrics._handler_label(
        {"route": None, "path": "/docs", "endpoint": lambda: None}
    ) == "/docs"

    # Unmatched 404: neither route nor endpoint → None (not recorded).
    assert metrics._handler_label({"route": None, "path": "/scanner-noise"}) is None


def test_setup_metrics_disabled_does_not_mount():
    app = FastAPI()
    metrics.setup_metrics(app, enabled=False)
    assert TestClient(app).get("/metrics").status_code == 404


async def test_timed_rag_retrieval_records_and_passes_through():
    @metrics.timed_rag_retrieval
    async def fake_retrieve():
        return (["a", "b", "c"], "context text")

    before = _hist_count(metrics.RAG_CONTEXT_CHUNKS)
    result = await fake_retrieve()

    # Return value is passed through untouched.
    assert result == (["a", "b", "c"], "context text")
    # One retrieval was observed (chunk count + latency).
    assert _hist_count(metrics.RAG_CONTEXT_CHUNKS) == before + 1
    assert _hist_count(metrics.RAG_RETRIEVAL_SECONDS) >= 1


async def test_timed_rag_retrieval_survives_unexpected_return_shape():
    @metrics.timed_rag_retrieval
    async def weird_retrieve():
        return "not a (sources, ctx) tuple"

    # Must not raise even though the return can't be unpacked into 2 items.
    assert await weird_retrieve() == "not a (sources, ctx) tuple"


def test_log_mutations_increments_citation_counter():
    from app.services.citation_guard import CitationMutation, log_mutations

    counter = metrics.CITATION_GUARD_MUTATIONS_TOTAL
    before = counter.labels(kind="unverified_title")._value.get()

    mutation = CitationMutation(
        kind="unverified_title",
        original="【《伪造经》第1卷】",
        replacement="《伪造经》",
        title="伪造经",
        original_juan=1,
        corrected_juan=None,
    )
    log_mutations(42, [mutation])
    assert counter.labels(kind="unverified_title")._value.get() == before + 1

    # Empty mutation list is a no-op (no spurious increments).
    log_mutations(42, [])
    assert counter.labels(kind="unverified_title")._value.get() == before + 1
