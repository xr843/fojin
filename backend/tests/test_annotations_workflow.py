"""Tests for annotation submit/review workflow."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.annotation import (
    create_annotation,
    submit_annotation,
    review_annotation,
)


def _make_annotation(**overrides):
    """Create a mock Annotation with defaults."""
    ann = MagicMock()
    ann.id = overrides.get("id", 1)
    ann.text_id = overrides.get("text_id", 100)
    ann.juan_num = overrides.get("juan_num", 1)
    ann.start_pos = overrides.get("start_pos", 0)
    ann.end_pos = overrides.get("end_pos", 10)
    ann.annotation_type = overrides.get("annotation_type", "note")
    ann.content = overrides.get("content", "test note")
    ann.user_id = overrides.get("user_id", 1)
    ann.status = overrides.get("status", "draft")
    return ann


@pytest.mark.anyio
async def test_submit_draft_to_pending():
    """submit_annotation should change status from draft to pending."""
    ann = _make_annotation(status="draft", user_id=1)
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = ann
    mock_session.execute.return_value = mock_result

    result = await submit_annotation(mock_session, annotation_id=1, user_id=1)
    assert result.status == "pending"
    mock_session.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_submit_non_draft_raises():
    """submit_annotation on a non-draft annotation should raise 400."""
    from fastapi import HTTPException

    ann = _make_annotation(status="pending", user_id=1)
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = ann
    mock_session.execute.return_value = mock_result

    with pytest.raises(HTTPException) as exc_info:
        await submit_annotation(mock_session, annotation_id=1, user_id=1)
    assert exc_info.value.status_code == 400


@pytest.mark.anyio
async def test_submit_wrong_user_raises():
    """submit_annotation by a different user should raise 403."""
    from fastapi import HTTPException

    ann = _make_annotation(status="draft", user_id=1)
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = ann
    mock_session.execute.return_value = mock_result

    with pytest.raises(HTTPException) as exc_info:
        await submit_annotation(mock_session, annotation_id=1, user_id=999)
    assert exc_info.value.status_code == 403


@pytest.mark.anyio
async def test_review_approve():
    """review_annotation with 'approve' should set status to approved."""
    ann = _make_annotation(status="pending", user_id=1)
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = ann
    mock_session.execute.return_value = mock_result

    with patch("app.services.annotation.AnnotationReview"):
        result = await review_annotation(mock_session, 1, reviewer_id=2, action="approve")
    assert result.status == "approved"


@pytest.mark.anyio
async def test_review_reject():
    """review_annotation with 'reject' should set status to rejected."""
    ann = _make_annotation(status="pending", user_id=1)
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = ann
    mock_session.execute.return_value = mock_result

    with patch("app.services.annotation.AnnotationReview"):
        result = await review_annotation(mock_session, 1, reviewer_id=2, action="reject")
    assert result.status == "rejected"


@pytest.mark.anyio
async def test_review_request_change():
    """review_annotation with 'request_change' should set status back to draft."""
    ann = _make_annotation(status="pending", user_id=1)
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = ann
    mock_session.execute.return_value = mock_result

    with patch("app.services.annotation.AnnotationReview"):
        result = await review_annotation(mock_session, 1, reviewer_id=2, action="request_change")
    assert result.status == "draft"


@pytest.mark.anyio
async def test_review_non_pending_raises():
    """review_annotation on a non-pending annotation should raise 400."""
    from fastapi import HTTPException

    ann = _make_annotation(status="draft", user_id=1)
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = ann
    mock_session.execute.return_value = mock_result

    with pytest.raises(HTTPException) as exc_info:
        await review_annotation(mock_session, 1, reviewer_id=2, action="approve")
    assert exc_info.value.status_code == 400
