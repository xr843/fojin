"""Annotation read-visibility scoping (BOLA fix).

The list/get read paths used to return every annotation for a text
regardless of owner or status, leaking other users' draft/pending/rejected
notes. Reads are now scoped to "approved (public) OR owned by the viewer".
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import NotFoundError
from app.services.annotation import (
    _visible_to,
    get_visible_annotation,
    list_annotations_for_text,
)


def _make_annotation(**overrides):
    ann = MagicMock()
    ann.id = overrides.get("id", 1)
    ann.user_id = overrides.get("user_id", 1)
    ann.status = overrides.get("status", "draft")
    return ann


def _session_returning(ann):
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = ann
    session.execute.return_value = result
    return session


# ── get_visible_annotation ───────────────────────────────────────────────

@pytest.mark.anyio
async def test_approved_visible_to_anonymous():
    ann = _make_annotation(status="approved", user_id=1)
    out = await get_visible_annotation(_session_returning(ann), 1, viewer_id=None)
    assert out is ann


@pytest.mark.anyio
async def test_draft_hidden_from_anonymous():
    ann = _make_annotation(status="draft", user_id=1)
    with pytest.raises(NotFoundError):
        await get_visible_annotation(_session_returning(ann), 1, viewer_id=None)


@pytest.mark.anyio
async def test_draft_hidden_from_other_user():
    ann = _make_annotation(status="pending", user_id=1)
    with pytest.raises(NotFoundError):
        await get_visible_annotation(_session_returning(ann), 1, viewer_id=999)


@pytest.mark.anyio
async def test_own_draft_visible_to_owner():
    ann = _make_annotation(status="draft", user_id=42)
    out = await get_visible_annotation(_session_returning(ann), 1, viewer_id=42)
    assert out is ann


# ── list_annotations_for_text query filter ───────────────────────────────

def _compiled_where(viewer_id):
    # _visible_to returns the SQLAlchemy clause the list query ANDs in.
    clause = _visible_to(viewer_id)
    return str(clause.compile(compile_kwargs={"literal_binds": True}))


def test_anonymous_filter_is_approved_only():
    sql = _compiled_where(None)
    assert "approved" in sql
    assert "user_id" not in sql


def test_viewer_filter_is_approved_or_own():
    sql = _compiled_where(7)
    assert "approved" in sql
    assert "user_id" in sql
    assert "7" in sql


@pytest.mark.anyio
async def test_list_passes_visibility_filter_into_query():
    captured = {}

    async def fake_execute(stmt):
        captured["stmt"] = stmt
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        return result

    session = AsyncMock()
    session.execute = fake_execute
    await list_annotations_for_text(session, text_id=100, juan_num=1, viewer_id=7)

    sql = str(captured["stmt"].compile(compile_kwargs={"literal_binds": True}))
    assert "approved" in sql and "user_id" in sql and "7" in sql
