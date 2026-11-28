"""游客断线找回：答案生成完后在 Redis 暂存 10 分钟，取回一次即删。

2026-11-28 实测：/chat 断网类失败 7 天 62 次，约三分之二是游客；服务端每次都已生成完并把整段
发出去（nginx 200），是在 Cloudflare → 浏览器这段丢了。登录用户能回库找回（76%），游客不落库，
一个都找不回。这里给游客一条同样的退路——只用浏览器随机生成的 32 位编号取，不进数据库、
不进任何历史；取一次就删，到期自动删。游客提示语相应写明「断线时临时保留 10 分钟以便找回」。
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

GUEST_RESULT_TTL_S = 600
_KEY = "chat:guest_result:{}"


def guest_result_key(request_id: str) -> str:
    return _KEY.format(request_id)


async def stash_guest_result(redis, request_id: str | None, payload: dict[str, Any]) -> bool:
    """暂存游客答案。没有 Redis / 没有编号时什么都不做；Redis 出错只记日志，不影响回答。"""
    if redis is None or not request_id:
        return False
    try:
        await redis.set(guest_result_key(request_id), json.dumps(payload, ensure_ascii=False), ex=GUEST_RESULT_TTL_S)
        return True
    except Exception as exc:  # 找回只是退路，绝不能让它打断回答
        logger.warning("guest result stash failed: %s", exc)
        return False


async def take_guest_result(redis, request_id: str) -> dict[str, Any] | None:
    """取回并删除（一次性）。没有或已过期返回 None。"""
    if redis is None:
        return None
    raw = await redis.getdel(guest_result_key(request_id))
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode()
    return json.loads(raw)


# --- 提前结束的诊断记录（2026-11-28）---
# 「一个字都没收到」（前端 silent_done）30 天 9 次：服务端约 1 秒就以 200 结束，但容器日志每次部署清空，
# 事后查不到是哪条路提前结束的。这里把每次提前结束的原因推进 Redis 列表，只留最近 200 条、保留 30 天，
# 不存提问内容（只存长度）。查看：docker exec fojin-redis redis-cli LRANGE chat:early_end 0 50
EARLY_END_KEY = "chat:early_end"
EARLY_END_KEEP = 200


async def note_early_end(redis, **fields: Any) -> None:
    if redis is None:
        return
    try:
        import time

        await redis.lpush(EARLY_END_KEY, json.dumps({"ts": int(time.time()), **fields}, ensure_ascii=False))
        await redis.ltrim(EARLY_END_KEY, 0, EARLY_END_KEEP - 1)
        await redis.expire(EARLY_END_KEY, 30 * 86400)
    except Exception as exc:  # 诊断记录绝不能影响回答
        logger.warning("early-end note failed: %s", exc)
