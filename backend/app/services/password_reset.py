"""忘记密码：管理员代发的一次性重置链接 + 登录页的找回申请 + 登录失败原因计数。

为什么不是「填邮箱自助收信」：fojin 没有发信服务，而且注册时从不验证邮箱
（``users.email_verified`` 只对 GitHub/Google 登录为真），有人填的是错邮箱、
甚至别人的邮箱。所以先走「用户申请 → 管理员核实 → 管理员把一次性链接发给他」，
邮件自助等量出需求再做（2026-11-09 决定，判据见 login 失败计数）。

安全约束：
- 链接里的令牌只在 Redis 存它的 sha256，不存明文；24 小时过期；GETDEL 原子消费，
  只能用一次。同一用户再生成一次，旧链接立即作废。
- 令牌绑定生成时的 ``password_version``：期间用户自己改过密码、退出过所有设备，
  链接就失效——管理员手里的旧链接不能拿来覆盖用户的新密码。
- 重置成功即 ``password_version + 1``：所有设备上的旧登录一并失效。
- 找回申请对外永远回同一句话，不暴露「这个账号存不存在」。
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import hash_password
from app.core.exceptions import ResetLinkInvalidError
from app.models.feedback import Feedback
from app.models.user import PasswordChangeAudit, User

logger = logging.getLogger(__name__)

RESET_TTL_SECONDS = 24 * 3600
_TOKEN_KEY = "pwreset:token:"  # + sha256(token) → {"uid":…, "pv":…}
_USER_KEY = "pwreset:user:"  # + uid → 该用户当前有效令牌的 sha256（换新时作废旧的）
_REQUEST_DEDUPE_KEY = "pwreset:req:"  # + uid → 24h 内只进一次收件箱
REQUEST_DEDUPE_SECONDS = 24 * 3600

# 登录失败原因计数：判断「要不要做邮件自助重置」的数据来源。容器日志每次部署
# 都会随容器重建清空，撑不起一个月的观察，所以落 Redis。
LOGIN_FAIL_DAY_KEY = "login:fail:"  # + YYYY-MM-DD → hash{reason: count}
LOGIN_BADPW_KEY = "login:badpw"  # zset uid → 最近一次「账号存在但密码错」的时间戳
LOGIN_FAIL_TTL = 120 * 24 * 3600

REQUEST_CONTENT_PREFIX = "【找回密码申请】"


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def issue_reset_token(redis, user: User) -> str:
    """生成一次性令牌并登记；同一用户此前的令牌立即作废。返回明文令牌（只此一次）。"""
    token = secrets.token_urlsafe(32)
    digest = _digest(token)
    old = await redis.get(f"{_USER_KEY}{user.id}")
    if old:
        old = old.decode() if isinstance(old, bytes) else old
        await redis.delete(f"{_TOKEN_KEY}{old}")
    payload = json.dumps({"uid": user.id, "pv": user.password_version or 0})
    await redis.set(f"{_TOKEN_KEY}{digest}", payload, ex=RESET_TTL_SECONDS)
    await redis.set(f"{_USER_KEY}{user.id}", digest, ex=RESET_TTL_SECONDS)
    return token


async def reset_password_with_token(
    db: AsyncSession,
    redis,
    token: str,
    new_password: str,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """凭一次性令牌设新密码。新密码强度已由 schema 校验——所以弱密码不会白白烧掉令牌。"""
    raw = await redis.getdel(f"{_TOKEN_KEY}{_digest(token)}")
    if not raw:
        raise ResetLinkInvalidError()
    data = json.loads(raw)
    user = (await db.execute(select(User).where(User.id == data["uid"]))).scalar_one_or_none()
    if user is None or not user.is_active or (user.password_version or 0) != data["pv"]:
        raise ResetLinkInvalidError()

    await redis.delete(f"{_USER_KEY}{user.id}")
    user.hashed_password = hash_password(new_password)
    user.password_version = (user.password_version or 0) + 1
    user.password_changed_at = datetime.now(UTC)
    db.add(
        PasswordChangeAudit(
            user_id=user.id,
            outcome="success",
            via="reset_link",
            ip=client_ip,
            user_agent=(user_agent[:500] if user_agent else None),
        )
    )
    await db.commit()
    logger.info("password_reset_success user_id=%s new_version=%s ip=%s", user.id, user.password_version, client_ip)


async def submit_reset_request(db: AsyncSession, redis, account: str, contact: str) -> None:
    """登录页「忘记密码」申请。匹配到账号就以该账号名义进管理员收件箱，否则只记数。

    调用方不论结果都回同一句话。24 小时内同一账号只进一次收件箱，防刷屏。
    """
    account = account.strip()
    user = (
        await db.execute(select(User).where(or_(User.username == account, User.email == account)))
    ).scalar_one_or_none()
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    if user is None:
        await _bump(redis, f"{LOGIN_FAIL_DAY_KEY}{day}", "reset_request_unmatched")
        logger.info("password_reset_request unmatched")
        return
    await _bump(redis, f"{LOGIN_FAIL_DAY_KEY}{day}", "reset_request")
    if redis is not None:
        try:
            fresh = await redis.set(f"{_REQUEST_DEDUPE_KEY}{user.id}", "1", ex=REQUEST_DEDUPE_SECONDS, nx=True)
        except Exception:  # Redis 挂了宁可重复进收件箱，也不能吞掉申请
            fresh = True
        if not fresh:
            logger.info("password_reset_request duplicate user_id=%s", user.id)
            return
    matched_by = "用户名" if user.username == account else "邮箱"
    db.add(
        Feedback(
            user_id=user.id,
            content=(
                f"{REQUEST_CONTENT_PREFIX}按{matched_by}匹配到账号「{user.username}」。"
                f"请先核实身份，再到「用户管理」为该账号生成重置链接；"
                f"能发到注册邮箱就发注册邮箱，留的联系方式与注册邮箱不一致时尤其要核实。"
            ),
            contact=contact.strip()[:200],
        )
    )
    await db.commit()
    logger.info("password_reset_request user_id=%s matched_by=%s", user.id, matched_by)


async def record_login_failure(redis, reason: str, user_id: int | None = None) -> None:
    """登录失败按原因记数（no_user / no_user_email_shape / bad_password / disabled）。

    只记内部 id，不记用户名、密码。Redis 不可用时静默跳过——计数不能拖垮登录。
    """
    if redis is None:
        return
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    try:
        await _bump(redis, f"{LOGIN_FAIL_DAY_KEY}{day}", reason)
        if user_id is not None:
            await redis.zadd(LOGIN_BADPW_KEY, {str(user_id): datetime.now(UTC).timestamp()})
            await redis.expire(LOGIN_BADPW_KEY, LOGIN_FAIL_TTL)
    except Exception:
        logger.warning("login failure counter: redis unavailable")


async def _bump(redis, key: str, field: str) -> None:
    if redis is None:
        return
    try:
        await redis.hincrby(key, field, 1)
        await redis.expire(key, LOGIN_FAIL_TTL)
    except Exception:
        logger.warning("password reset counter: redis unavailable")
