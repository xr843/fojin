"""滑动续期的判定策略（纯函数，无网络/无库/无真实时钟）。

背景：JWT 只有 8 小时且无续期，隔夜回访的用户会被静默降级成游客——配额从
200/天 掉到按 IP 共享的 10 次，会话不再存进账号，而且没有任何提示。之前量过
52% 的 chat 会话会撞到。滑动续期让"还在用的人"永不掉线，闲置 token 照常老化。
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.services.token_renewal import RENEW_AFTER_FRACTION, original_issued_at, should_renew

EXPIRE_MINUTES = 60 * 8
MAX_DAYS = 30
NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def claims(*, expires_in: timedelta, oit: datetime | None = None) -> dict:
    payload = {"sub": "1", "pwd_v": 0, "exp": int((NOW + expires_in).timestamp())}
    if oit is not None:
        payload["oit"] = int(oit.timestamp())
    return payload


def renew(c: dict) -> bool:
    return should_renew(c, now=NOW, expire_minutes=EXPIRE_MINUTES, absolute_max_days=MAX_DAYS)


# ── 半程阈值 ────────────────────────────────────────────────────────────


def test_fresh_token_is_not_renewed():
    """刚签发的 token 不续——否则每个请求都换一张，白白多签。

    承重点：只断言"快过期时会续"是不够的，一个无条件续期的实现照样能过。
    """
    assert renew(claims(expires_in=timedelta(hours=8))) is False
    assert renew(claims(expires_in=timedelta(hours=5))) is False


def test_token_past_half_life_is_renewed():
    assert renew(claims(expires_in=timedelta(hours=3))) is True
    assert renew(claims(expires_in=timedelta(minutes=1))) is True


def test_the_boundary_itself():
    """约定：剩余 **小于等于** 半程即续。把阈值钉死，改 RENEW_AFTER_FRACTION 会红。

    两边都不能省：只钉"半程续"而不钉"多一秒不续"的话，一个无条件续期的实现
    照样能过。
    """
    half = timedelta(minutes=EXPIRE_MINUTES * (1 - RENEW_AFTER_FRACTION))
    assert renew(claims(expires_in=half)) is True
    assert renew(claims(expires_in=half + timedelta(seconds=1))) is False


# ── 绝对上限：活跃会话不能靠续期永生 ────────────────────────────────────


def test_session_older_than_cap_is_not_renewed():
    old = NOW - timedelta(days=MAX_DAYS, minutes=1)
    assert renew(claims(expires_in=timedelta(hours=1), oit=old)) is False


def test_session_just_inside_cap_is_still_renewed():
    almost = NOW - timedelta(days=MAX_DAYS) + timedelta(minutes=1)
    assert renew(claims(expires_in=timedelta(hours=1), oit=almost)) is True


def test_oit_survives_a_chain_of_renewals():
    """承重点：续期必须沿用原始 oit，否则每续一次上限就重新计时，等于没有上限。

    模拟连续续期——exp 一直是新的，oit 保持不变，第 31 天必须停下。
    """
    began = NOW - timedelta(days=MAX_DAYS, hours=1)
    fresh_looking = claims(expires_in=timedelta(hours=1), oit=began)
    assert renew(fresh_looking) is False, "oit 被沿用时应当触到上限"
    # 反面：如果实现把 oit 重置成"现在"，它就会一直续下去
    reset_oit = claims(expires_in=timedelta(hours=1), oit=NOW)
    assert renew(reset_oit) is True, "这正是不能重置 oit 的原因"


# ── 老 token（还没有 oit 这个字段）────────────────────────────────────


def test_legacy_token_without_oit_recovers_its_origin_from_exp():
    """上线前签发的 token 没有 oit，但 exp = 签发时刻 + 有效期，可精确还原。"""
    c = claims(expires_in=timedelta(hours=1))  # 无 oit
    began = original_issued_at(c, expire_minutes=EXPIRE_MINUTES)
    assert began == NOW + timedelta(hours=1) - timedelta(minutes=EXPIRE_MINUTES)
    assert renew(c) is True  # 7 小时前签的，远未到 30 天上限


# ── 说不的其余理由 ──────────────────────────────────────────────────────


def test_expired_token_is_never_renewed():
    """已过期的 token 不续。生产上不可达（它根本没通过鉴权），但函数自身要自洽。"""
    assert renew(claims(expires_in=timedelta(seconds=-1))) is False


@pytest.mark.parametrize("bad", [{}, {"exp": None}, {"exp": "not-a-number"}, {"exp": object()}])
def test_unparseable_claims_never_renew(bad):
    """判不出来就不续——绝不能因为解析失败而误发一张新证。"""
    assert should_renew(bad, now=NOW, expire_minutes=EXPIRE_MINUTES, absolute_max_days=MAX_DAYS) is False


def test_unparseable_oit_falls_back_to_no_renewal():
    c = claims(expires_in=timedelta(hours=1))
    c["oit"] = "garbage"
    assert renew(c) is False
