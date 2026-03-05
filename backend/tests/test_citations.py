"""Tests for citation generation."""

import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.anyio
async def test_citation_chicago():
    """Chicago style citation should include title, translator, CBETA ID."""
    from app.services.citation import generate_citation

    fake_text = MagicMock()
    fake_text.id = 1
    fake_text.title_zh = "般若波罗蜜多心经"
    fake_text.translator = "玄奘"
    fake_text.dynasty = "唐"
    fake_text.cbeta_id = "T0251"

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_text
    mock_session.execute.return_value = mock_result

    result = await generate_citation(mock_session, text_id=1, style="chicago")
    assert result.style == "chicago"
    assert "般若波罗蜜多心经" in result.citation
    assert "玄奘" in result.citation
    assert "T0251" in result.citation


@pytest.mark.anyio
async def test_citation_apa():
    """APA style citation."""
    from app.services.citation import generate_citation

    fake_text = MagicMock()
    fake_text.id = 1
    fake_text.title_zh = "心经"
    fake_text.translator = "玄奘"
    fake_text.dynasty = "唐"
    fake_text.cbeta_id = "T0251"

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_text
    mock_session.execute.return_value = mock_result

    result = await generate_citation(mock_session, text_id=1, style="apa")
    assert result.style == "apa"
    assert "心经" in result.citation


@pytest.mark.anyio
async def test_citation_mla():
    """MLA style citation."""
    from app.services.citation import generate_citation

    fake_text = MagicMock()
    fake_text.id = 1
    fake_text.title_zh = "心经"
    fake_text.translator = "玄奘"
    fake_text.dynasty = "唐"
    fake_text.cbeta_id = "T0251"

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_text
    mock_session.execute.return_value = mock_result

    result = await generate_citation(mock_session, text_id=1, style="mla")
    assert result.style == "mla"
    assert "心经" in result.citation


@pytest.mark.anyio
async def test_citation_harvard():
    """Harvard style citation."""
    from app.services.citation import generate_citation

    fake_text = MagicMock()
    fake_text.id = 1
    fake_text.title_zh = "心经"
    fake_text.translator = "玄奘"
    fake_text.dynasty = "唐"
    fake_text.cbeta_id = "T0251"

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_text
    mock_session.execute.return_value = mock_result

    result = await generate_citation(mock_session, text_id=1, style="harvard")
    assert result.style == "harvard"
    assert "心经" in result.citation


@pytest.mark.anyio
async def test_citation_not_found():
    """Citation for non-existent text should raise 404."""
    from fastapi import HTTPException
    from app.services.citation import generate_citation

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    with pytest.raises(HTTPException) as exc_info:
        await generate_citation(mock_session, text_id=999)
    assert exc_info.value.status_code == 404
