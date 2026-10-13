"""fojin研读交流群 —— 站内定向邀请。

只邀请服务器上名单里的用户（重度使用者），给他们看开发者的微信二维码。
名单与二维码都**不进仓库、不进前端包**，只放在服务器数据目录
``/data/community/``（docker-compose 已把宿主 ``./data`` 挂成 ``/data``）：

- ``invite.json``：``{"enabled": true, "user_ids": [12, 34, ...]}``
- ``wechat-qr.png``（或 ``.jpg``）：开发者个人微信名片码

安全默认关：目录、文件缺失，JSON 坏掉，``enabled`` 不是 ``true``，或名单里
没有这个人——一律当作「不邀请」，卡片对任何人都不出现，也拿不到二维码。
删掉 ``invite.json`` 即可立即停用，无需部署。

「不了，谢谢」记在 Redis 的一个集合里（按用户 id），换设备也不会再弹。
Redis 不可用时同样按「不显示」处理，宁可少弹一次，不反复打扰。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

COMMUNITY_DIR = Path("/data/community")
INVITE_FILE = "invite.json"
QR_CANDIDATES = (("wechat-qr.png", "image/png"), ("wechat-qr.jpg", "image/jpeg"))
# 二维码图片的上限：一张名片码几百 KB，超过说明放错了文件，不往外发。
QR_MAX_BYTES = 2 * 1024 * 1024
DISMISSED_KEY = "community_invite:dismissed:v1"


@dataclass(frozen=True)
class InviteConfig:
    user_ids: frozenset[int]


def load_config(base: Path | None = None) -> InviteConfig | None:
    """读取邀请名单；任何不对劲都返回 None（= 不邀请任何人）。"""
    path = (base or COMMUNITY_DIR) / INVITE_FILE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        logger.warning("community invite: %s unreadable or not valid JSON; invite disabled", path)
        return None
    if not isinstance(raw, dict) or raw.get("enabled") is not True:
        return None
    ids = raw.get("user_ids")
    if not isinstance(ids, list):
        return None
    # bool 是 int 的子类，true/false 不能被当成用户 1/0。
    valid = frozenset(i for i in ids if isinstance(i, int) and not isinstance(i, bool) and i > 0)
    return InviteConfig(user_ids=valid) if valid else None


def is_listed(user_id: int, base: Path | None = None) -> bool:
    cfg = load_config(base)
    return cfg is not None and user_id in cfg.user_ids


def load_qr(base: Path | None = None) -> tuple[bytes, str] | None:
    """返回（图片字节, MIME）；没有或过大时返回 None。"""
    root = base or COMMUNITY_DIR
    for name, mime in QR_CANDIDATES:
        path = root / name
        try:
            if not path.is_file() or path.stat().st_size > QR_MAX_BYTES:
                continue
            return path.read_bytes(), mime
        except OSError:
            continue
    return None


async def is_dismissed(redis, user_id: int) -> bool | None:
    """True/False；Redis 不可用时返回 None，由调用方按「不显示」处理。"""
    if redis is None:
        return None
    try:
        return bool(await redis.sismember(DISMISSED_KEY, str(user_id)))
    except Exception:  # Redis 抖动不该让页面报错
        logger.warning("community invite: redis unavailable when reading dismissal")
        return None


async def mark_dismissed(redis, user_id: int) -> bool:
    if redis is None:
        return False
    try:
        await redis.sadd(DISMISSED_KEY, str(user_id))
        return True
    except Exception:
        logger.warning("community invite: redis unavailable when recording dismissal")
        return False
