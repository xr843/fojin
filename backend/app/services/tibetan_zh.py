"""藏译汉稿（tibetan-canon-zh）——只读转发 + 缓存。

源项目 https://github.com/xr843/tibetan-canon-zh 是唯一真源，佛津只做展示。

⚠️ 这些是 **AI 译稿，未经懂藏文的专家审定**，不能被当作经文引用。因此本模块：
  - **绝不**写入 PostgreSQL、不进 Elasticsearch、不进 AI 问答（chat / RAG）的任何
    数据源，也不做向量化。它只在 Redis 里放一份带时间戳的缓存副本。
  - 不要从 chat / rag_retrieval / search / embedding 等模块 import 本模块
    （tests/test_tibetan_zh.py 有守卫测试）。

为什么由服务器去拉：佛津读者约四分之三在中国大陆，raw.githubusercontent.com
在大陆常常打不开，浏览器不能直连 GitHub。

缓存：Redis（两个 backend 副本共用同一份，各自进程内缓存会让两边各拉一遍、
内容也可能一时不一致）。值里记着拉取时间，约 1 小时内算新鲜；过期后先试上游，
上游失败就继续返回旧副本（键本身保留 30 天），并把下一次重试推迟 5 分钟，
免得上游宕机时每个请求都去撞一次超时。Redis 不可用时退回进程内字典。

安全（防 SSRF / 路径穿越）：请求里的 ``{id}`` 只用来在索引里查表；拉取用的
URL 一律由固定前缀 + **索引里的** ``path`` 组成，path 还要过白名单校验并逐段转义；
不跟随重定向；响应体超过上限即中止。索引里的 md/pdf/docx 链接只保留指向源仓库
的 https 地址（前端会把它们渲染成链接）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

REPO_URL = "https://github.com/xr843/tibetan-canon-zh"
RAW_BASE = "https://raw.githubusercontent.com/xr843/tibetan-canon-zh/main/"
INDEX_URL = RAW_BASE + "site/data/translations.json"

FRESH_SECONDS = 3600  # 约 1 小时内不回源
RETRY_AFTER_FAILURE_SECONDS = 300  # 上游失败后，旧副本再顶 5 分钟才重试
KEEP_SECONDS = 30 * 24 * 3600  # Redis 键保留时长：上游长期不可用时的兜底
MAX_DOC_BYTES = 6 * 1024 * 1024  # 目前最大一部 T-2978 约 2.5 MB
MAX_INDEX_BYTES = 1024 * 1024
TIMEOUT = httpx.Timeout(20.0, connect=5.0)

_CACHE_PREFIX = "tibetan_zh:v1:"
_INDEX_KEY = _CACHE_PREFIX + "index"

ID_RE = re.compile(r"^[A-Z]{1,3}-\d{1,5}$")
# 仓库内相对路径：不以 / 开头、不含 .. 段、不含 \ ? # % : 与空白，必须是 .md
_PATH_RE = re.compile(r"^[^/\\?#%:\s][^\\?#%:\s]*\.md$")
_LINK_PREFIX = REPO_URL + "/"
_TEXT_FIELDS = ("title", "au", "part", "cat", "rv")
_LINK_FIELDS = ("md", "pdf", "docx")


class UpstreamUnavailable(Exception):
    """上游拉不到，且没有任何旧副本可用。"""


class UnknownTranslation(Exception):
    """编号格式不对，或不在索引里。"""


# ---------------------------------------------------------------- 缓存层

_local_cache: dict[str, str] = {}
_locks: dict[str, asyncio.Lock] = {}


async def _cache_get(redis: Any, key: str) -> dict | None:
    raw = None
    if redis is not None:
        try:
            raw = await redis.get(key)
        except Exception as exc:  # Redis 故障不该让页面挂掉
            logger.warning("tibetan_zh: redis get %s failed: %s", key, exc)
    if raw is None:
        raw = _local_cache.get(key)
    if raw is None:
        return None
    try:
        entry = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return entry if isinstance(entry, dict) and "t" in entry and "v" in entry else None


async def _cache_set(redis: Any, key: str, entry: dict) -> None:
    raw = json.dumps(entry, ensure_ascii=False)
    if redis is not None:
        try:
            await redis.set(key, raw, ex=KEEP_SECONDS)
            _local_cache.pop(key, None)
            return
        except Exception as exc:
            logger.warning("tibetan_zh: redis set %s failed: %s", key, exc)
    _local_cache[key] = raw


def _http_client() -> httpx.AsyncClient:
    # 测试里替换成 MockTransport。不跟随重定向：raw.githubusercontent.com 本身不跳转，
    # 跳转只可能把我们带去别处。
    return httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False)


async def _fetch_bytes(url: str, limit: int) -> bytes:
    async with _http_client() as client, client.stream("GET", url) as resp:
        if resp.status_code != 200:
            raise UpstreamUnavailable(f"HTTP {resp.status_code} from {url}")
        declared = resp.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > limit:
            raise UpstreamUnavailable(f"{url}: {declared} bytes exceeds limit {limit}")
        buf = bytearray()
        async for chunk in resp.aiter_bytes():
            buf.extend(chunk)
            if len(buf) > limit:
                raise UpstreamUnavailable(f"{url}: body exceeds limit {limit}")
        return bytes(buf)


async def _cached(redis: Any, key: str, load) -> tuple[Any, float, bool]:
    """返回 (值, 拉取时间, 是否为过期旧副本)。``load`` 是回源协程工厂。"""
    entry = await _cache_get(redis, key)
    now = time.time()
    if entry is not None and now - entry["t"] < FRESH_SECONDS:
        return entry["v"], entry.get("fetched", entry["t"]), bool(entry.get("stale"))

    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        # 等锁期间别的协程可能已经刷新过
        entry = await _cache_get(redis, key) or entry
        now = time.time()
        if entry is not None and now - entry["t"] < FRESH_SECONDS:
            return entry["v"], entry.get("fetched", entry["t"]), bool(entry.get("stale"))
        try:
            value = await load()
        # 有意兜住一切异常：上游/网络/解析之外，连 httpx 客户端都可能建不起来（例如环境里配了
        # SOCKS 代理而没装 socksio，本地实测撞到过）。任何失败都应退回旧副本或 503，不能 500。
        except Exception as exc:
            if entry is None:
                logger.warning("tibetan_zh: upstream failed for %s, no cache: %s", key, exc)
                raise UpstreamUnavailable(str(exc)) from exc
            logger.warning("tibetan_zh: upstream failed for %s, serving stale copy: %s", key, exc)
            # 推迟下一次重试：把时间戳挪到「再过 RETRY_AFTER 秒就过期」
            retry_t = max(entry["t"], now - FRESH_SECONDS + RETRY_AFTER_FAILURE_SECONDS)
            fetched = entry.get("fetched", entry["t"])
            await _cache_set(redis, key, {"t": retry_t, "v": entry["v"], "fetched": fetched, "stale": True})
            return entry["v"], fetched, True
        await _cache_set(redis, key, {"t": now, "v": value, "fetched": now})
        return value, now, False


# ---------------------------------------------------------------- 索引


def _sanitize_index(raw: Any) -> list[dict]:
    if not isinstance(raw, dict):
        raise ValueError("translations.json is not an object")
    items: list[dict] = []
    for tid, rec in raw.items():
        if not isinstance(tid, str) or not ID_RE.match(tid) or not isinstance(rec, dict):
            continue
        path = rec.get("path")
        if not isinstance(path, str) or not _PATH_RE.match(path) or ".." in path.split("/"):
            continue
        item: dict[str, Any] = {"id": tid, "path": path}
        for f in _TEXT_FIELDS:
            v = rec.get(f)
            item[f] = v.strip() if isinstance(v, str) else ""
        for f in _LINK_FIELDS:
            v = rec.get(f)
            item[f] = v if isinstance(v, str) and v.startswith(_LINK_PREFIX) else None
        items.append(item)
    if not items:
        raise ValueError("translations.json has no usable entries")
    return items


async def _load_index() -> list[dict]:
    body = await _fetch_bytes(INDEX_URL, MAX_INDEX_BYTES)
    return _sanitize_index(json.loads(body.decode("utf-8")))


async def get_index(redis: Any) -> tuple[list[dict], float, bool]:
    return await _cached(redis, _INDEX_KEY, _load_index)


def public_item(item: dict) -> dict:
    """对外的索引条目：不暴露内部用的 path。"""
    return {k: v for k, v in item.items() if k != "path"}


# ---------------------------------------------------------------- 正文


async def get_document(redis: Any, tid: str) -> tuple[str, dict, float, bool]:
    """返回 (Markdown 原文, 索引条目, 拉取时间, 是否旧副本)。"""
    if not ID_RE.match(tid):
        raise UnknownTranslation(tid)
    items, _, _ = await get_index(redis)
    item = next((it for it in items if it["id"] == tid), None)
    if item is None:
        raise UnknownTranslation(tid)
    # URL 只由固定前缀 + 索引里（已校验的）path 组成，用户输入不参与拼接
    url = RAW_BASE + quote(item["path"], safe="/")

    async def load() -> str:
        return (await _fetch_bytes(url, MAX_DOC_BYTES)).decode("utf-8")

    # 缓存键含 path：源仓库改了文件路径，旧副本自然失效
    key = f"{_CACHE_PREFIX}doc:{tid}:{item['path']}"
    text, fetched, stale = await _cached(redis, key, load)
    return text, item, fetched, stale
