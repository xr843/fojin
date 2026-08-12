"""Public streamable-HTTP edge for the fojin MCP server.

This module owns everything that only matters when fojin-mcp is *hosted* (at
``mcp.fojin.ai``) rather than launched over stdio by a local client:

- :class:`RateLimitMiddleware` — per-client-IP sliding-window limiter. The
  hosted endpoint is anonymous, so the client IP (``CF-Connecting-IP`` when
  behind Cloudflare/nginx, else the socket peer) is the quota key. This is the
  middle belt of a three-belt design: Cloudflare WAF outside, this per-IP
  window here, and the backend's own limits (with the MCP host exempted)
  underneath.
- :class:`AccessLogMiddleware` — one structured JSON line per request to the
  ``fojin_mcp.access`` logger: the adoption observability the stdio server
  never had. The tool name is read out of the JSON-RPC body as it streams past
  (see :class:`_ToolSniffer` for why it is not read from a header).
- :func:`build_http_app` — assembles the Starlette app: MCP streamable HTTP in
  stateless + json_response mode (each call is one plain JSON POST — no long
  SSE streams, so Cloudflare's proxy timeout/buffering never enters the
  picture), DNS-rebinding Host validation pinned to the public hostnames, and
  the two middlewares above.

Everything here is import-safe without uvicorn; only ``serve_http`` needs it.
"""

from __future__ import annotations

import json
import logging
import time
from collections import deque
from typing import Any

from starlette.applications import Starlette

DEFAULT_RATE_LIMIT = 30          # requests per window per client IP
DEFAULT_RATE_WINDOW = 60.0       # seconds
DEFAULT_PUBLIC_HOSTS = ["mcp.fojin.ai"]
_EXEMPT_PATHS = frozenset({"/healthz"})

access_logger = logging.getLogger("fojin_mcp.access")


def _header(scope: dict[str, Any], name: bytes) -> str | None:
    for k, v in scope.get("headers") or ():
        if k == name:
            return v.decode("latin-1")
    return None


def client_ip_from_scope(scope: dict[str, Any], *, trust_proxy_headers: bool) -> str:
    """Client IP for quota/logging.

    ``CF-Connecting-IP`` is set by Cloudflare and passed through by our nginx;
    ``X-Real-IP`` is what nginx sets from its own real-ip resolution. Only
    trusted when the process sits behind that chain (the deployment binds to
    loopback, so untrusted direct exposure never sees these headers spoofed
    from the internet — but the flag keeps local/dev runs honest)."""
    if trust_proxy_headers:
        for h in (b"cf-connecting-ip", b"x-real-ip"):
            val = _header(scope, h)
            if val:
                return val.strip()
    client = scope.get("client")
    return client[0] if client else "unknown"


class RateLimitMiddleware:
    """Sliding-window per-IP rate limiter (pure ASGI, in-process memory).

    In-process state is correct for the single-container deployment; if the
    endpoint ever scales to N containers the window becomes N× looser, which
    the outer Cloudflare WAF rule still bounds."""

    def __init__(
        self,
        app: Any,
        *,
        limit: int = DEFAULT_RATE_LIMIT,
        window: float = DEFAULT_RATE_WINDOW,
        trust_proxy_headers: bool = True,
    ) -> None:
        self.app = app
        self.limit = limit
        self.window = window
        self.trust_proxy_headers = trust_proxy_headers
        self._hits: dict[str, deque[float]] = {}

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope.get("path") in _EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return
        ip = client_ip_from_scope(scope, trust_proxy_headers=self.trust_proxy_headers)
        now = time.monotonic()
        dq = self._hits.setdefault(ip, deque())
        while dq and now - dq[0] > self.window:
            dq.popleft()
        if len(dq) >= self.limit:
            retry_after = max(1, int(self.window - (now - dq[0])) + 1)
            body = json.dumps(
                {
                    "error": "rate_limited",
                    "detail": (
                        f"fojin MCP allows {self.limit} requests per "
                        f"{int(self.window)}s per client; retry after "
                        f"{retry_after}s."
                    ),
                }
            ).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 429,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"retry-after", str(retry_after).encode()),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        dq.append(now)
        # Opportunistic GC so one-off IPs don't accumulate forever.
        if len(self._hits) > 10_000:
            cutoff = now - self.window
            self._hits = {
                k: v for k, v in self._hits.items() if v and v[-1] >= cutoff
            }
        await self.app(scope, receive, send)


class _ToolSniffer:
    """Pulls the tool name out of a JSON-RPC request body as it streams past.

    Why this exists: until 2026-08-12 the access log read the tool name from an
    ``Mcp-Name`` request header, which no client sends. Every real call was
    logged as ``"tool": null`` — the one field the log was built for. The only
    entries that ever carried a name came from scanners that happen to set that
    optional header, so the log answered "which tool do bots announce" instead
    of "which tool is anyone using".

    Reads chunks as they flow rather than buffering the whole body and
    replaying it: a JSON-RPC call arrives in one chunk in practice, and a
    middleware that holds every request body in memory is a liability on an
    endpoint anyone can POST to. Parsing is attempted on each chunk until the
    JSON is complete, and abandoned past ``LIMIT`` — this is observability, so
    losing a name costs a log field, never a request.
    """

    LIMIT = 64 * 1024

    def __init__(self) -> None:
        self._buf = bytearray()
        self._done = False
        self.tool: str | None = None

    def feed(self, chunk: bytes) -> None:
        if self._done or not chunk:
            return
        self._buf += chunk
        if len(self._buf) > self.LIMIT:
            self._give_up()
            return
        try:
            payload = json.loads(self._buf)
        except ValueError:
            return  # 还没收全，等下一块
        self._done = True
        self._buf.clear()
        self.tool = self._name(payload)

    def _give_up(self) -> None:
        self._done = True
        self._buf.clear()

    @staticmethod
    def _name(payload: Any) -> str | None:
        # 批量请求是一个数组；取第一个真正的工具调用。
        for one in payload if isinstance(payload, list) else [payload]:
            if isinstance(one, dict) and one.get("method") == "tools/call":
                name = (one.get("params") or {}).get("name")
                if isinstance(name, str) and name:
                    return name
        return None


class AccessLogMiddleware:
    """One JSON line per request: ts, ip, method, path, status, ms, tool, ua.

    This is the server's adoption dashboard — `docker logs` + grep answers
    "who is actually calling which tool", the question the PyPI package could
    never answer."""

    def __init__(self, app: Any, *, trust_proxy_headers: bool = True) -> None:
        self.app = app
        self.trust_proxy_headers = trust_proxy_headers

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.monotonic()
        status_holder = {"status": 0}
        sniffer = _ToolSniffer()

        async def receive_wrapper() -> dict[str, Any]:
            message = await receive()
            if message.get("type") == "http.request":
                sniffer.feed(message.get("body") or b"")
            return message

        async def send_wrapper(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        finally:
            access_logger.info(
                "%s",
                json.dumps(
                    {
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                        "ip": client_ip_from_scope(
                            scope, trust_proxy_headers=self.trust_proxy_headers
                        ),
                        "method": scope.get("method"),
                        "path": scope.get("path"),
                        "status": status_holder["status"],
                        "ms": round((time.monotonic() - start) * 1000, 1),
                        # 请求体优先；Mcp-Name 头留作兜底，有客户端会设它。
                        "tool": sniffer.tool or _header(scope, b"mcp-name"),
                        "ua": _header(scope, b"user-agent"),
                    },
                    ensure_ascii=False,
                ),
            )


def build_http_app(
    *,
    public_hosts: list[str] | None = None,
    rate_limit: int = DEFAULT_RATE_LIMIT,
    rate_window: float = DEFAULT_RATE_WINDOW,
    trust_proxy_headers: bool = True,
    local_port: int | None = None,
) -> Starlette:
    """Build the hosted Starlette app around the MCP server.

    stateless_http + json_response: every tool call is a single self-contained
    JSON POST — safe behind Cloudflare's proxy (no SSE stream to buffer or
    time out) and safe under multi-worker uvicorn (no in-process session).
    """
    from mcp.server.transport_security import TransportSecuritySettings

    from .server import mcp  # deferred: avoid import cycle at module load

    hosts = list(public_hosts) if public_hosts is not None else list(DEFAULT_PUBLIC_HOSTS)
    allowed: list[str] = []
    for h in hosts:
        allowed.extend([h, f"{h}:443", f"{h}:80"])
    for local in ("127.0.0.1", "localhost"):
        allowed.append(f"{local}:{local_port}" if local_port else local)
        if local_port:
            allowed.append(local)
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=sorted(set(allowed)),
        # MCP clients are not browsers and send no Origin; an Origin-bearing
        # (browser) request has no business here, so none are allowed.
        allowed_origins=[],
    )
    app = mcp.streamable_http_app(
        json_response=True,
        stateless_http=True,
        transport_security=security,
    )
    # Order matters: log outermost so 429s are logged too.
    app.add_middleware(
        RateLimitMiddleware,
        limit=rate_limit,
        window=rate_window,
        trust_proxy_headers=trust_proxy_headers,
    )
    app.add_middleware(AccessLogMiddleware, trust_proxy_headers=trust_proxy_headers)
    return app


def serve_http(
    *,
    host: str,
    port: int,
    public_hosts: list[str] | None = None,
    rate_limit: int = DEFAULT_RATE_LIMIT,
    rate_window: float = DEFAULT_RATE_WINDOW,
    trust_proxy_headers: bool = True,
) -> None:
    """Run the hosted endpoint under uvicorn (requires the ``http`` extra)."""
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "The streamable-http transport needs uvicorn: "
            "pip install 'fojin-mcp[http]'"
        ) from exc
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    app = build_http_app(
        public_hosts=public_hosts,
        rate_limit=rate_limit,
        rate_window=rate_window,
        trust_proxy_headers=trust_proxy_headers,
        local_port=port,
    )
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=False)
