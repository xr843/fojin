"""Rename / pin a chat session (PATCH /chat/sessions/{id}).

Covers the service and the request schema. The sidebar's "..." menu is the only
caller today, but the endpoint is ownership-scoped and therefore worth pinning
down independently of the UI that drives it.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import AccessDeniedError, NotFoundError, ValidationError
from app.schemas.chat import SessionUpdateRequest
from app.services.chat_sessions import update_session


def _make_session(**overrides):
    cs = MagicMock()
    cs.id = overrides.get("id", 7)
    cs.user_id = overrides.get("user_id", 1)
    cs.title = overrides.get("title", "旧标题")
    cs.pinned = overrides.get("pinned", False)
    return cs


def _db_returning(cs):
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = cs
    db.execute.return_value = result
    return db


# ── service ──────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_rename_sets_title_and_commits():
    cs = _make_session()
    db = _db_returning(cs)
    out = await update_session(db, 7, user_id=1, title="《心经》逐句读")
    assert out.title == "《心经》逐句读"
    assert cs.pinned is False  # untouched field stays put
    db.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_pin_sets_flag_without_touching_title():
    cs = _make_session(title="原名")
    db = _db_returning(cs)
    await update_session(db, 7, user_id=1, pinned=True)
    assert cs.pinned is True
    assert cs.title == "原名"


@pytest.mark.anyio
async def test_unpin_is_not_swallowed_by_the_none_check():
    """`pinned=False` is falsy — an `if pinned:` implementation would silently
    no-op here and the user's un-pin click would do nothing."""
    cs = _make_session(pinned=True)
    db = _db_returning(cs)
    await update_session(db, 7, user_id=1, pinned=False)
    assert cs.pinned is False
    db.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_empty_patch_is_rejected_rather_than_a_silent_ok():
    db = _db_returning(_make_session())
    with pytest.raises(ValidationError):
        await update_session(db, 7, user_id=1)
    db.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_whitespace_title_rejected_at_the_service_too():
    cs = _make_session(title="原名")
    db = _db_returning(cs)
    with pytest.raises(ValidationError):
        await update_session(db, 7, user_id=1, title="   ")
    assert cs.title == "原名"
    db.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_other_users_session_is_denied():
    db = _db_returning(_make_session(user_id=2))
    with pytest.raises(AccessDeniedError):
        await update_session(db, 7, user_id=1, pinned=True)
    db.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_missing_session_is_404_not_500():
    db = _db_returning(None)
    with pytest.raises(NotFoundError):
        await update_session(db, 7, user_id=1, title="x")


@pytest.mark.anyio
async def test_ownership_is_checked_before_any_write():
    """Order matters: a title assigned before the ownership check would be
    flushed by any later commit in the same session."""
    cs = _make_session(user_id=2, title="别人的会话")
    db = _db_returning(cs)
    with pytest.raises(AccessDeniedError):
        await update_session(db, 7, user_id=1, title="改名")
    assert cs.title == "别人的会话"


# ── request schema ───────────────────────────────────────────────────────

def test_schema_strips_surrounding_whitespace():
    assert SessionUpdateRequest(title="  《法华经》  ").title == "《法华经》"


def test_schema_rejects_whitespace_only_title():
    with pytest.raises(PydanticValidationError):
        SessionUpdateRequest(title="　 ")


def test_schema_rejects_empty_title():
    with pytest.raises(PydanticValidationError):
        SessionUpdateRequest(title="")


def test_schema_rejects_overlong_title():
    with pytest.raises(PydanticValidationError):
        SessionUpdateRequest(title="经" * 201)


def test_schema_allows_pin_only_patch():
    payload = SessionUpdateRequest(pinned=True)
    assert payload.title is None
    assert payload.pinned is True


# ── 迁移与 ORM 的一致性 ──────────────────────────────────────────────────

def test_migration_0174_and_the_orm_agree_on_the_column():
    """整个 backend/tests 没有真库往返（conftest 里 PG/ES/Redis 全是 mock），
    而 alembic-dry-run 只跑 upgrade/downgrade、从不 SELECT。两边合起来的后果是：
    迁移里写 "pinned"、ORM 里写成别的名字，全套测试照样绿，直到生产上第一次
    查会话列表才炸。这条把两个字面量钉在一起。"""
    import re
    from pathlib import Path

    from app.models.chat import ChatSession

    src = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0174_add_chat_sessions_pinned.py"
    body = src.read_text(encoding="utf-8")
    m = re.search(r'op\.add_column\(\s*"([^"]+)",\s*sa\.Column\(\s*"([^"]+)"', body)
    assert m, "迁移 0174 的 add_column 形态变了，这条检查已失效——请同步更新"
    table, column = m.group(1), m.group(2)

    assert table == ChatSession.__tablename__
    assert column in ChatSession.__table__.columns
    # 迁移建的是 NOT NULL DEFAULT false；ORM 若声明成可空，读回来会是 None
    # 而不是 False，前端 `!!s.pinned` 虽兜得住，排序 `pinned.desc()` 却会错乱。
    assert ChatSession.__table__.columns[column].nullable is False
