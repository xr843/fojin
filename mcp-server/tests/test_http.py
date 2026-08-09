"""Tests for the hosted streamable-HTTP edge (fojin_mcp.http).

Uses Starlette's TestClient against the real MCP ASGI app in stateless
json_response mode, with FojinClient swapped for a mocked transport — so these
exercise the actual MCP protocol path (tools/list, tools/call) plus the edge
concerns (rate limiting, Host validation, healthz) without any network.
"""

from __future__ import annotations

import json

import httpx
import pytest
from starlette.testclient import TestClient

import fojin_mcp.server as server_mod
from fojin_mcp.client import FojinClient
from fojin_mcp.http import build_http_app

MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def _rpc(method: str, params: dict | None = None, id_: int = 1) -> dict:
    msg: dict = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        msg["params"] = params
    return msg


@pytest.fixture()
def mock_fojin_client():
    """Install a FojinClient with a mocked transport as the shared client."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/search/semantic":
            return httpx.Response(200, json={"total": 1, "results": [
                {"text_id": 5, "juan_num": 1, "title_zh": "心經",
                 "cbeta_id": "T0251", "snippet": "色即是空",
                 "similarity_score": 0.9}]})
        return httpx.Response(404, json={"detail": "unexpected " + request.url.path})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://test")
    client = FojinClient("http://test/api", client=http)
    server_mod._client = client
    yield client
    server_mod._client = None


def _test_app(**kwargs):
    kwargs.setdefault("public_hosts", ["testserver"])
    return build_http_app(**kwargs)


def test_healthz_ok():
    with TestClient(_test_app()) as tc:
        resp = tc.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "fojin-mcp"


def test_tools_list_over_streamable_http():
    with TestClient(_test_app()) as tc:
        resp = tc.post("/mcp", json=_rpc("tools/list"), headers=MCP_HEADERS)
    assert resp.status_code == 200, resp.text
    tools = {t["name"] for t in resp.json()["result"]["tools"]}
    assert tools == {
        "search_corpus", "read_passage", "get_parallels",
        "lookup_dictionary", "lookup_entity", "resolve_urn", "verify_quote",
    }


def test_tools_call_search_corpus(mock_fojin_client):
    with TestClient(_test_app()) as tc:
        resp = tc.post(
            "/mcp",
            json=_rpc("tools/call", {
                "name": "search_corpus",
                "arguments": {"query": "空", "limit": 3},
            }),
            headers=MCP_HEADERS,
        )
    assert resp.status_code == 200, resp.text
    result = resp.json()["result"]
    assert not result.get("isError"), result
    # Bare-dict tools carry their JSON in content[0].text (no output schema →
    # no structuredContent).
    payload = json.loads(result["content"][0]["text"])
    assert payload["results"][0]["urn"] == "fojin:cbeta/T0251.1"


def test_rate_limit_kicks_in_and_healthz_exempt():
    app = _test_app(rate_limit=2, rate_window=60.0)
    with TestClient(app) as tc:
        codes = [
            tc.post("/mcp", json=_rpc("tools/list"), headers=MCP_HEADERS).status_code
            for _ in range(3)
        ]
        limited = tc.post("/mcp", json=_rpc("tools/list"), headers=MCP_HEADERS)
        health = tc.get("/healthz")
    assert codes[0] == 200 and codes[1] == 200
    assert codes[2] == 429
    assert limited.status_code == 429
    assert "retry-after" in {k.lower() for k in limited.headers}
    assert limited.json()["error"] == "rate_limited"
    assert health.status_code == 200          # exempt from the limiter


def test_rate_limit_keyed_on_cf_connecting_ip():
    app = _test_app(rate_limit=1, rate_window=60.0)
    with TestClient(app) as tc:
        a1 = tc.post("/mcp", json=_rpc("tools/list"),
                     headers={**MCP_HEADERS, "CF-Connecting-IP": "203.0.113.7"})
        a2 = tc.post("/mcp", json=_rpc("tools/list"),
                     headers={**MCP_HEADERS, "CF-Connecting-IP": "203.0.113.7"})
        b1 = tc.post("/mcp", json=_rpc("tools/list"),
                     headers={**MCP_HEADERS, "CF-Connecting-IP": "198.51.100.9"})
    assert a1.status_code == 200
    assert a2.status_code == 429              # same client exhausted
    assert b1.status_code == 200              # different client unaffected


def test_host_header_validation_rejects_unknown_host():
    """DNS-rebinding protection: an app built for mcp.fojin.ai must reject the
    TestClient's default Host (testserver)."""
    app = build_http_app(public_hosts=["mcp.fojin.ai"])
    with TestClient(app) as tc:
        resp = tc.post("/mcp", json=_rpc("tools/list"), headers=MCP_HEADERS)
    assert resp.status_code >= 400
