"""When a still-valid access token should be swapped for a fresh one.

滑动续期的判定逻辑。

fojin issues an 8-hour JWT and has no refresh token, so a reader who comes back
the next day is silently demoted to a guest: the quota drops from 200/day to an
IP-shared 10/day and their conversation stops being saved to their account.
Nothing tells them — ``get_optional_user`` returns ``None`` for an expired token
exactly as it does for no token at all. Measured earlier: 52% of chat sessions
run into the expiry.

Sliding renewal fixes that without a refresh-token store: while someone is
actively using the site, any authenticated request past the token's half-life
hands back a fresh one. Idle tokens still age out normally.

This module is pure policy so it can be unit-tested without network, DB or
clock — the probing/IO lives in ``TokenRenewalMiddleware`` (app/main.py). It
deliberately does **not** verify signatures or identity: by the time it is
consulted the request has already authenticated, including the
``password_version`` check that makes a password change revoke old tokens.
Renewing on signature validity alone would mint a fresh token for a session the
user had just revoked.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

# Renew only in the token's second half. Renewing on every request would mint a
# token per API call (a chat page fires several) for no added lifetime.
RENEW_AFTER_FRACTION = 0.5


def original_issued_at(claims: dict[str, Any], *, expire_minutes: int) -> datetime | None:
    """When this *session* began, as opposed to when this token was minted.

    Carried across renewals in ``oit`` so that a chain of renewed tokens still
    remembers its own start and cannot outrun the absolute cap.

    Tokens minted before ``oit`` existed carry only ``exp`` — but ``exp`` is
    always issue-time + ``expire_minutes``, so their origin is recoverable
    exactly. (This holds while ``jwt_expire_minutes`` is unchanged; if it is
    ever changed, pre-existing tokens are mis-dated by the difference, at worst
    granting or denying one renewal window near the cap.)
    """
    oit = claims.get("oit")
    if oit is not None:
        try:
            return datetime.fromtimestamp(int(oit), UTC)
        except (TypeError, ValueError, OSError, OverflowError):
            return None
    exp = claims.get("exp")
    if exp is None:
        return None
    try:
        return datetime.fromtimestamp(int(exp), UTC) - timedelta(minutes=expire_minutes)
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def should_renew(
    claims: dict[str, Any],
    *,
    now: datetime,
    expire_minutes: int,
    absolute_max_days: int,
) -> bool:
    """True when this token is worth replacing on the current response.

    Four ways to answer no:

    * no ``exp`` — not a token this policy understands;
    * already expired — renewal is for live sessions. An expired token never
      authenticated in the first place, so this is unreachable in production,
      but stating it here keeps the function honest on its own terms;
    * still in its first half — nothing to gain, and it would mint a token per
      request;
    * older than the absolute cap — an active session must not become immortal
      just because someone keeps clicking. Past the cap they log in again.
    """
    exp = claims.get("exp")
    if exp is None:
        return False
    try:
        expires_at = datetime.fromtimestamp(int(exp), UTC)
    except (TypeError, ValueError, OSError, OverflowError):
        return False

    if expires_at <= now:
        return False

    full_life = timedelta(minutes=expire_minutes)
    if expires_at - now > full_life * (1 - RENEW_AFTER_FRACTION):
        return False

    began = original_issued_at(claims, expire_minutes=expire_minutes)
    if began is None:
        return False
    return now - began < timedelta(days=absolute_max_days)
