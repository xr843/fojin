"""Prometheus metrics for FoJin.

A small, dependency-light observability layer: a ``BaseHTTPMiddleware`` that
records per-handler HTTP request count + latency, a couple of chat-pipeline
metrics, and a ``/metrics`` endpoint — all on ``prometheus_client`` directly.

Why not ``prometheus-fastapi-instrumentator``: its route-name resolver walks
``app.routes`` and assumes every entry has ``.path``. FastAPI 0.139's routing
introduces internal ``_IncludedRouter`` tree nodes (``BaseRoute`` without
``.path``), which makes that walk raise ``AttributeError`` on this app. We read
the already-matched route off ``request.scope["route"]`` instead, which is
robust across FastAPI versions and never touches ``app.routes``.

Exposure model — ``/metrics`` lives at the app **root**, not under ``/api``.
``frontend/nginx.conf`` proxies only specific paths to the backend (``/api/``,
``/docs``, ``/redoc``, ``/openapi.json``, the SSR/SEO routes …) and has no
catch-all ``location / { proxy_pass backend }``, so ``/metrics`` is not
reachable from the public internet — a Prometheus on the docker network scrapes
``fojin-backend:8000/metrics`` directly. Do **not** add an nginx location for
it. Set ``METRICS_ENABLED=false`` to not mount it at all.
"""

from __future__ import annotations

import functools
import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, TypeVar

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

if TYPE_CHECKING:
    from fastapi import FastAPI
    from starlette.requests import Request

logger = logging.getLogger(__name__)

# --- HTTP metrics ---------------------------------------------------------

# Per-handler request count and latency. ``handler`` is the route *template*
# (e.g. ``/api/texts/{tid}``), never the raw path, so cardinality stays bounded.
HTTP_REQUESTS_TOTAL = Counter(
    "fojin_http_requests_total",
    "HTTP requests by method, handler (route template) and status code",
    ["method", "handler", "status"],
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "fojin_http_request_duration_seconds",
    "HTTP request latency by method and handler (route template)",
    ["method", "handler"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Handlers whose metrics we deliberately drop: the scrape endpoint itself and
# the liveness probes (hit twice-daily by CD + on every container health check,
# which would otherwise dominate the request counters).
_EXCLUDED_PATHS = frozenset({"/metrics", "/api/health", "/api/version"})

# --- Custom application metrics -------------------------------------------

# RAG retrieval latency. The pgvector recall + rerank pipeline is the dominant
# non-LLM cost of a chat turn; watch p95 here for regressions. Buckets span the
# observed 0.05s–13s range (13s ~= cold-cache / precise-retrieval-miss tail).
RAG_RETRIEVAL_SECONDS = Histogram(
    "fojin_rag_retrieval_seconds",
    "Wall-clock time in retrieve_rag_context (pgvector recall + rerank)",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 13.0),
)

# Context chunks handed to the LLM per retrieval (capped at MAX_CONTEXT_CHUNKS).
# A spike in the 0-bucket = retrieval returning nothing, worth alerting on.
RAG_CONTEXT_CHUNKS = Histogram(
    "fojin_rag_context_chunks",
    "Number of context chunks returned by retrieve_rag_context",
    buckets=(0, 1, 2, 3, 4, 5, 6, 8, 10),
)

# Anti-hallucination guard rewrites. Rising = the model is inventing citations
# the whitelist rejects (a retrieval or prompt regression), the single worst
# failure mode for a scholarly tool. Labelled by CitationMutation.kind
# (unverified_title / fascicle_corrected).
CITATION_GUARD_MUTATIONS_TOTAL = Counter(
    "fojin_citation_guard_mutations_total",
    "Model citations rewritten/stripped by the anti-hallucination guard",
    ["kind"],
)


_Retrieval = TypeVar("_Retrieval", bound=Callable[..., Awaitable])


def timed_rag_retrieval(fn: _Retrieval) -> _Retrieval:
    """Decorate an async ``(...) -> (sources, context_text)`` retrieval
    function with latency + chunk-count instrumentation.

    Transparent wrapper (``functools.wraps``) — it does not touch the wrapped
    body or change its signature/return, so callers and tests are unaffected.
    Metric recording never raises into the retrieval path.
    """

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        with RAG_RETRIEVAL_SECONDS.time():
            result = await fn(*args, **kwargs)
        try:
            sources, _context_text = result
            RAG_CONTEXT_CHUNKS.observe(len(sources))
        except (TypeError, ValueError):
            # Never let instrumentation break retrieval on an unexpected shape.
            pass
        return result

    return wrapper  # type: ignore[return-value]


def _handler_label(scope) -> str | None:
    """Derive a low-cardinality ``handler`` label from a request scope.

    Returns a route *template* with path params collapsed to ``{name}`` — but
    built from ``scope["path"]`` (the full path, prefix included), NOT
    ``route.path``: FastAPI 0.139's ``_IncludedRouter`` makes a matched route's
    ``.path`` the router-relative sub-path (``/chat/models`` for
    ``/api/chat/models``), which would collide distinct routers (e.g. the
    ``/api/search`` API route vs the root ``/search`` SSR route).

    - No matched route (404 / scanner noise): ``None`` → not recorded, so the
      label can't explode on arbitrary paths. Starlette built-ins
      (``/openapi.json``, ``/docs``, ``/redoc``) carry no ``route`` but do set
      ``endpoint`` and have fixed paths, so those are kept as-is.
    - Matched route, no path params: the full path is already the template.
    - Matched route with params: each param value is replaced with ``{name}``
      at a ``/`` boundary. Longest value first, so a short value that is a
      substring of another param's value can't clobber it; ``{x:path}``
      converters (values containing ``/``, e.g. the SEO dict headwords) are
      handled by the same boundary regex.
    """
    route = scope.get("route")
    raw = scope.get("path", "")
    if route is None:
        return raw if scope.get("endpoint") is not None else None
    params = scope.get("path_params") or {}
    if not params:
        return raw
    label = raw
    for name, value in sorted(params.items(), key=lambda kv: -len(str(kv[1]))):
        label = re.sub(
            rf"(?<=/){re.escape(str(value))}(?=/|$)",
            f"{{{name}}}",
            label,
            count=1,
        )
    return label


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record request count + latency, keyed by the matched route template.

    Runs outermost so it times the whole stack; the route match is read off the
    shared scope after ``call_next`` returns (see ``_handler_label``).
    """

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)

        if request.scope.get("path") in _EXCLUDED_PATHS:
            return response
        handler = _handler_label(request.scope)
        if handler is None:
            return response  # unmatched (404) — don't record

        elapsed = time.perf_counter() - start
        method = request.method
        HTTP_REQUEST_DURATION_SECONDS.labels(method, handler).observe(elapsed)
        HTTP_REQUESTS_TOTAL.labels(method, handler, str(response.status_code)).inc()
        return response


async def _metrics_endpoint(_request: Request) -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def setup_metrics(app: FastAPI, *, enabled: bool = True) -> None:
    """Install the metrics middleware and mount ``/metrics``.

    No-op when ``enabled`` is False (nothing mounted). Call once per app at
    import time — ``add_middleware`` must run before the app starts serving.
    """
    if not enabled:
        logger.info("metrics: disabled (METRICS_ENABLED=false); /metrics not mounted")
        return
    app.add_middleware(MetricsMiddleware)
    app.add_route("/metrics", _metrics_endpoint, include_in_schema=False)
    logger.info("metrics: /metrics mounted (network-internal — keep it out of nginx)")
