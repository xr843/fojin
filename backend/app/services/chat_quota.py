"""Chat quota + message validation.

Extracted verbatim from ``app.services.chat`` (P1-3 god-file split).
``_check_daily_quota``'s explicit-UPDATE shape and the schema/service
length-cap sync note both carry incident history — read the docstrings
before touching.
"""

import logging
from datetime import date

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import QuotaExceededError, ServiceError, ValidationError
from app.models.user import User

logger = logging.getLogger(__name__)

# Free daily limits for users without their own API key
FREE_DAILY_LIMIT_USER = 200      # Logged-in users — effectively unlimited for normal use, caps abuse
FREE_DAILY_LIMIT_ANONYMOUS = 10  # Anonymous users (encourage registration)


async def _check_daily_quota(db: AsyncSession, user: User) -> None:
    """Check and increment daily free chat quota. Raises QuotaExceededError if exceeded.

    The increment runs as an **explicit UPDATE** rather than mutating
    ``user`` attributes because ``user`` is loaded by ``get_optional_user``
    on a *different* session from the one threaded into the streaming
    chat path (see send_message_stream's prep-phase session). A
    ``user.attr = value`` mutation against a session that doesn't own
    the row gets silently dropped by ``flush()`` — no SQL is emitted,
    quota stops incrementing, and free-tier limits stop applying.
    The UPDATE-by-id form works regardless of which session loaded
    ``user`` originally. The in-memory ``user`` is also patched so the
    caller's view stays consistent within the same request.
    """
    today = date.today()
    same_day = user.last_chat_date == today
    current_count = user.daily_chat_count if same_day else 0
    if current_count >= FREE_DAILY_LIMIT_USER:
        raise QuotaExceededError(limit=FREE_DAILY_LIMIT_USER)
    new_count = current_count + 1
    await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(daily_chat_count=new_count, last_chat_date=today)
    )
    await db.flush()
    # Keep the caller's in-memory User in sync with what we just wrote
    # so any later attribute reads in the same request are coherent.
    user.daily_chat_count = new_count
    user.last_chat_date = today


def _anon_quota_key(client_ip: str) -> str:
    """Redis key for anonymous daily chat quota by IP."""
    today = date.today().isoformat()
    return f"chat:anon:{client_ip}:{today}"


async def get_anonymous_quota_used(redis, client_ip: str) -> int:
    """Get the number of chats used today by an anonymous IP."""
    if not redis:
        return 0
    try:
        val = await redis.get(_anon_quota_key(client_ip))
        return int(val) if val else 0
    except Exception:
        return 0


async def _check_anonymous_quota(redis, client_ip: str) -> None:
    """Check and increment anonymous daily quota via Redis. Raises QuotaExceededError if exceeded."""
    if not redis:
        raise ServiceError("服务暂时不可用，请稍后重试")
    key = _anon_quota_key(client_ip)
    try:
        current = await redis.incr(key)
        if current == 1:
            await redis.expire(key, 86400)  # 24h TTL
        if current > FREE_DAILY_LIMIT_ANONYMOUS:
            raise QuotaExceededError(limit=FREE_DAILY_LIMIT_ANONYMOUS)
    except QuotaExceededError:
        raise
    except Exception:
        logger.warning("Redis anonymous quota check failed", exc_info=True)


def _validate_message(message: str) -> None:
    """Validate chat message content.

    The length cap must stay aligned with ``ChatRequest.message.max_length``
    in app/schemas/chat.py — if the schema admits a longer message but
    this service-layer check rejects it, the result is a stream-internal
    ValidationError that surfaces in the UI as a generic
    "请求失败，请重试" with no breadcrumb until you look at backend logs
    (PR #651). Keep the two numbers in sync.
    """
    if not message or not message.strip():
        raise ValidationError("消息不能为空")
    if len(message) > 20000:
        raise ValidationError("消息长度不能超过20000字")


