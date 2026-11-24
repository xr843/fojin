"""藏译汉稿转发接口：正常、缓存命中、上游失败回退旧副本、非法编号 404、体积上限、
路径/链接白名单，以及「不进数据库 / ES / RAG」的守卫。上游一律 mock。"""

import json
import re
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import tibetan_zh as api_mod
from app.services import tibetan_zh as tz

INDEX = {
    "T-2796": {
        "title": "真实光明论",
        "au": "莲花戒",
        "part": "丹珠尔",
        "cat": "中观部",
        "rv": "经两层 AI 审核",
        "path": "translations/tengyur/T-2796_真实光明论.md",
        "md": "https://github.com/xr843/tibetan-canon-zh/blob/main/translations/tengyur/x.md",
        "pdf": "https://github.com/xr843/tibetan-canon-zh/releases/download/translations/T-2796.pdf",
        "docx": "javascript:alert(1)",
    },
    # path 试图穿越目录 → 整条丢弃
    "T-9999": {"title": "坏", "path": "../../etc/passwd.md"},
    # 编号格式不对 → 丢弃
    "../x": {"title": "坏", "path": "translations/x.md"},
}
DOC = "# 真实光明论\n\n> བོད་སྐད་དུ།\n\n汉译〔校注 1〕。\n"


class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value
        return True


class Upstream:
    """可切换的假上游：记录请求的 URL，可设为失败。"""

    def __init__(self):
        self.calls: list[str] = []
        self.fail = False
        self.doc = DOC.encode("utf-8")

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append(url)
        if self.fail:
            return httpx.Response(502)
        if url == tz.INDEX_URL:
            return httpx.Response(200, content=json.dumps(INDEX, ensure_ascii=False).encode())
        if url.startswith(tz.RAW_BASE + "translations/tengyur/T-2796_"):
            return httpx.Response(200, content=self.doc)
        return httpx.Response(404)


@pytest.fixture(autouse=True)
def _reset_local_state():
    tz._local_cache.clear()
    tz._locks.clear()
    yield
    tz._local_cache.clear()
    tz._locks.clear()


@pytest.fixture
def upstream(monkeypatch):
    up = Upstream()
    monkeypatch.setattr(
        tz,
        "_http_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(up.handler), follow_redirects=False),
    )
    return up


@pytest.fixture
def redis():
    return FakeRedis()


@pytest_asyncio.fixture
async def client(redis):
    app = FastAPI()
    app.include_router(api_mod.router, prefix="/api")
    app.state.redis = redis
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def _age_all_entries(redis: FakeRedis, seconds: float) -> None:
    for k, raw in redis.store.items():
        entry = json.loads(raw)
        entry["t"] -= seconds
        redis.store[k] = json.dumps(entry, ensure_ascii=False)


# ------------------------------------------------------------------ 正常


async def test_index_is_sanitized(client, upstream):
    r = await client.get("/api/tibetan-zh/index")
    assert r.status_code == 200
    body = r.json()
    assert body["stale"] is False
    assert [it["id"] for it in body["items"]] == ["T-2796"]
    item = body["items"][0]
    assert item["title"] == "真实光明论" and item["rv"] == "经两层 AI 审核"
    assert "path" not in item  # 内部字段不外露
    assert item["pdf"].startswith("https://github.com/xr843/tibetan-canon-zh/")
    assert item["docx"] is None  # 非源仓库链接被丢弃


async def test_document_returns_markdown(client, upstream):
    r = await client.get("/api/tibetan-zh/T-2796")
    assert r.status_code == 200
    assert r.text == DOC
    assert r.headers["content-type"].startswith("text/markdown")
    assert "X-Upstream-Stale" not in r.headers
    # 拉取地址来自索引里的 path（逐段转义），不是用户输入
    assert upstream.calls[-1] == tz.RAW_BASE + "translations/tengyur/T-2796_%E7%9C%9F%E5%AE%9E%E5%85%89%E6%98%8E%E8%AE%BA.md"


# ------------------------------------------------------------------ 缓存命中


async def test_second_request_is_served_from_cache(client, upstream, redis):
    await client.get("/api/tibetan-zh/T-2796")
    n = len(upstream.calls)
    assert n == 2  # 索引 + 正文
    r = await client.get("/api/tibetan-zh/T-2796")
    r2 = await client.get("/api/tibetan-zh/index")
    assert r.status_code == 200 and r.text == DOC and r2.status_code == 200
    assert len(upstream.calls) == n  # 一次都没有回源
    assert any(k.startswith("tibetan_zh:v1:doc:T-2796") for k in redis.store)


async def test_expired_cache_is_refreshed(client, upstream, redis):
    await client.get("/api/tibetan-zh/T-2796")
    _age_all_entries(redis, tz.FRESH_SECONDS + 1)
    upstream.doc = "# 新版\n".encode()
    r = await client.get("/api/tibetan-zh/T-2796")
    assert r.text == "# 新版\n"
    assert "X-Upstream-Stale" not in r.headers


# ------------------------------------------------------------------ 上游失败


async def test_upstream_failure_falls_back_to_stale_copy(client, upstream, redis):
    await client.get("/api/tibetan-zh/T-2796")
    _age_all_entries(redis, tz.FRESH_SECONDS + 1)
    upstream.fail = True
    r = await client.get("/api/tibetan-zh/T-2796")
    assert r.status_code == 200
    assert r.text == DOC
    assert r.headers["X-Upstream-Stale"] == "1"
    idx = await client.get("/api/tibetan-zh/index")
    assert idx.status_code == 200 and idx.json()["stale"] is True

    # 失败之后 5 分钟内不再回源（上游宕机时不让每个请求都去撞超时）
    n = len(upstream.calls)
    r = await client.get("/api/tibetan-zh/T-2796")
    assert r.status_code == 200 and len(upstream.calls) == n
    assert r.headers["X-Upstream-Stale"] == "1"  # 仍标明是旧副本

    # 重试窗口过后上游恢复：拿到新内容，旧副本标记消失
    _age_all_entries(redis, tz.RETRY_AFTER_FAILURE_SECONDS + 1)
    upstream.fail = False
    r = await client.get("/api/tibetan-zh/T-2796")
    assert r.status_code == 200 and "X-Upstream-Stale" not in r.headers


async def test_upstream_failure_without_cache_is_503(client, upstream):
    upstream.fail = True
    assert (await client.get("/api/tibetan-zh/index")).status_code == 503
    assert (await client.get("/api/tibetan-zh/T-2796")).status_code == 503


async def test_client_construction_error_degrades_instead_of_500(client, upstream, redis, monkeypatch):
    """httpx 客户端建不起来（如 SOCKS 代理缺 socksio）：有旧副本给旧副本，没有给 503，不能 500。"""
    await client.get("/api/tibetan-zh/T-2796")
    _age_all_entries(redis, tz.FRESH_SECONDS + 1)

    def broken():
        raise ImportError("Using SOCKS proxy, but the 'socksio' package is not installed.")

    monkeypatch.setattr(tz, "_http_client", broken)
    r = await client.get("/api/tibetan-zh/T-2796")
    assert r.status_code == 200 and r.headers["X-Upstream-Stale"] == "1"
    redis.store.clear()
    tz._local_cache.clear()
    assert (await client.get("/api/tibetan-zh/index")).status_code == 503


async def test_oversized_document_is_rejected(client, upstream, monkeypatch):
    monkeypatch.setattr(tz, "MAX_DOC_BYTES", 10)
    r = await client.get("/api/tibetan-zh/T-2796")
    assert r.status_code == 503


async def test_works_without_redis(upstream):
    app = FastAPI()
    app.include_router(api_mod.router, prefix="/api")  # app.state 没有 redis
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        assert (await ac.get("/api/tibetan-zh/T-2796")).text == DOC
        n = len(upstream.calls)
        assert (await ac.get("/api/tibetan-zh/T-2796")).text == DOC
        assert len(upstream.calls) == n  # 进程内缓存命中


# ------------------------------------------------------------------ 非法 id


@pytest.mark.parametrize(
    "tid",
    [
        "T-0001",  # 格式对但索引里没有
        "T-9999",  # 索引里有但 path 非法，已被丢弃
        "x",
        "..%2F..%2Fetc%2Fpasswd",
        "T-2796.md",
        "T-2796%3Fa=1",
    ],
)
async def test_unknown_or_malformed_id_is_404(client, upstream, tid):
    r = await client.get(f"/api/tibetan-zh/{tid}")
    assert r.status_code == 404
    # 只可能请求过索引，绝不会请求任何拼了用户输入的地址
    assert all(u == tz.INDEX_URL for u in upstream.calls)


async def test_malformed_id_does_not_even_fetch_index(client, upstream):
    r = await client.get("/api/tibetan-zh/not-an-id")
    assert r.status_code == 404
    assert upstream.calls == []


def test_path_whitelist():
    ok = {"T-1": {"path": "translations/a/b_（中）.md"}}
    assert tz._sanitize_index(ok)[0]["path"] == "translations/a/b_（中）.md"
    for bad in ["/abs.md", "a/../b.md", "a\\b.md", "a?.md", "a#b.md", "a%2e.md", "https://x/a.md", "a.txt", "a b.md"]:
        with pytest.raises(ValueError):
            tz._sanitize_index({"T-1": {"path": bad}})


async def test_redirects_are_not_followed(client, upstream, monkeypatch):
    def handler(request):
        upstream.calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/"})

    monkeypatch.setattr(
        tz, "_http_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)
    )
    assert (await client.get("/api/tibetan-zh/index")).status_code == 503
    assert upstream.calls == [tz.INDEX_URL]


# ------------------------------------------------------------------ 守卫：不进 DB / ES / RAG


BACKEND = Path(__file__).resolve().parents[1]


def test_module_touches_no_database_or_search_index():
    for rel in ("app/services/tibetan_zh.py", "app/api/tibetan_zh.py"):
        src = (BACKEND / rel).read_text(encoding="utf-8")
        imports = "\n".join(line for line in src.splitlines() if re.match(r"\s*(from|import)\s", line))
        for forbidden in ("app.database", "app.models", "sqlalchemy", "elasticsearch", "embedding", "rag"):
            assert forbidden not in imports, f"{rel} imports {forbidden}"


def test_no_chat_or_retrieval_code_reads_tibetan_zh():
    hits = []
    for p in (BACKEND / "app").rglob("*.py"):
        rel = p.relative_to(BACKEND).as_posix()
        if rel in ("app/services/tibetan_zh.py", "app/api/tibetan_zh.py", "app/main.py"):
            continue
        if "tibetan_zh" in p.read_text(encoding="utf-8"):
            hits.append(rel)
    assert hits == [], f"AI 译稿不得接入其他模块（尤其 chat/RAG/检索）: {hits}"


def test_main_app_mounts_routes():
    from app.main import app

    # 新版 FastAPI 把 include_router 收成嵌套节点，app.routes 里看不到子路径；用 OpenAPI 判
    paths = set(app.openapi()["paths"])
    assert "/api/tibetan-zh/index" in paths
    assert "/api/tibetan-zh/{tid}" in paths


def test_fresh_window_is_about_an_hour():
    assert 1800 <= tz.FRESH_SECONDS <= 7200
    assert tz.MAX_DOC_BYTES >= 3 * 1024 * 1024  # T-2978 约 2.5 MB 要放得下
