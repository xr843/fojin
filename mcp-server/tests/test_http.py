"""Tests for the hosted streamable-HTTP edge (fojin_mcp.http).

Uses Starlette's TestClient against the real MCP ASGI app in stateless
json_response mode, with FojinClient swapped for a mocked transport — so these
exercise the actual MCP protocol path (tools/list, tools/call) plus the edge
concerns (rate limiting, Host validation, healthz) without any network.
"""

from __future__ import annotations

import logging
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
        "commentaries",
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


# --- 访问日志真的记下了工具名 --------------------------------------------
#
# 2026-08-12 之前它记的是 Mcp-Name 请求头，而没有客户端发这个头：40 小时生产
# 日志里每一次真实调用都是 "tool": null，唯一带上名字的反而是碰巧设了这个可选
# 头的扫描器。日志于是回答了「机器人自称在调什么」，而不是「谁在用什么」。


def _access_lines(caplog):
    return [json.loads(r.message) for r in caplog.records
            if r.name == "fojin_mcp.access"]


def test_access_log_records_the_tool_actually_called(mock_fojin_client, caplog):
    caplog.set_level(logging.INFO, logger="fojin_mcp.access")
    with TestClient(_test_app()) as tc:
        tc.post("/mcp", json=_rpc("tools/call", {
            "name": "search_corpus", "arguments": {"query": "空", "limit": 3},
        }), headers=MCP_HEADERS)
    calls = [ln for ln in _access_lines(caplog) if ln["path"] == "/mcp"]
    assert calls and calls[-1]["tool"] == "search_corpus"


def test_access_log_leaves_tool_null_for_non_tool_traffic(caplog):
    """别的 MCP 方法也带 params.name —— 只看 name 就会把它们记成工具调用。

    故意用 prompts/get 而不是 tools/list：tools/list 压根没有 params.name，
    拿它来测「不是工具调用就不记名字」等于没测（把方法判断删掉，那种写法照样
    全绿——试过）。爬虫打的正是这一类方法，记错了整份采用数据就废了。
    """
    caplog.set_level(logging.INFO, logger="fojin_mcp.access")
    with TestClient(_test_app()) as tc:
        tc.post("/mcp", json=_rpc("prompts/get", {"name": "not-a-tool"}),
                headers=MCP_HEADERS)
    calls = [ln for ln in _access_lines(caplog) if ln["path"] == "/mcp"]
    assert calls and calls[-1]["tool"] is None


def test_sniffer_survives_a_body_split_across_chunks():
    from fojin_mcp.http import _ToolSniffer

    body = json.dumps(_rpc("tools/call", {"name": "commentaries",
                                          "arguments": {"quote": "應無所住"}})).encode()
    s = _ToolSniffer()
    for i in range(0, len(body), 7):        # 切碎，模拟分块到达
        s.feed(body[i:i + 7])
    assert s.tool == "commentaries"


def test_sniffer_gives_up_on_an_oversized_body_instead_of_hoarding_it():
    """可观测性不能变成任何人都能 POST 的内存负担——丢一个日志字段，不丢请求。"""
    from fojin_mcp.http import _ToolSniffer

    s = _ToolSniffer()
    s.feed(b'{"method":"tools/call","params":{"name":"x","arguments":{"q":"'
           + b"\xe7\xa9\xba" * _ToolSniffer.LIMIT)
    assert s.tool is None
    assert not s._buf
