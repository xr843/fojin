"""藏译汉稿：转发 tibetan-canon-zh 的索引与 Markdown 正文（只读）。

⚠️ AI 译稿，未经懂藏文的专家审定——只做展示，绝不写入数据库、不进 Elasticsearch、
不进 AI 问答（chat/RAG）。缓存与安全约束见 services/tibetan_zh.py。
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from app.services import tibetan_zh as tz

router = APIRouter(prefix="/tibetan-zh", tags=["tibetan-zh"])

# 浏览器可短暂缓存；服务端另有约 1 小时的 Redis 缓存。
_CACHE_CONTROL = "public, max-age=600"


def _redis(request: Request):
    return getattr(request.app.state, "redis", None)


@router.get("/index")
async def tibetan_zh_index(request: Request):
    """全部译稿的索引（编号、书名、作者、部、部类、审核情况、源文件/PDF/Word 链接）。"""
    try:
        items, fetched, stale = await tz.get_index(_redis(request))
    except tz.UpstreamUnavailable:
        raise HTTPException(status_code=503, detail="tibetan-canon-zh index unavailable") from None
    return JSONResponse(
        {
            "repo": tz.REPO_URL,
            "fetched_at": int(fetched),
            "stale": stale,
            "items": [tz.public_item(it) for it in items],
        },
        headers={"Cache-Control": _CACHE_CONTROL},
    )


@router.get("/{tid}")
async def tibetan_zh_document(tid: str, request: Request):
    """某一部译稿的 Markdown 原文。``tid`` 只能是索引里存在的编号，否则 404。"""
    try:
        text, _item, fetched, stale = await tz.get_document(_redis(request), tid)
    except tz.UnknownTranslation:
        raise HTTPException(status_code=404, detail="unknown translation id") from None
    except tz.UpstreamUnavailable:
        raise HTTPException(status_code=503, detail="tibetan-canon-zh document unavailable") from None
    headers = {"Cache-Control": _CACHE_CONTROL, "X-Fetched-At": str(int(fetched))}
    if stale:
        headers["X-Upstream-Stale"] = "1"
    return Response(content=text, media_type="text/markdown; charset=utf-8", headers=headers)
