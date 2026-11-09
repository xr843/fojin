"""采纳数据源推荐时自动建的条目必须是下线草稿，不能当场上线（2026-11-09）。"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.source_suggestions import _create_data_source
from app.models.source import DataSource


@pytest.mark.anyio
async def test_accepted_suggestion_becomes_an_unpublished_draft():
    db = MagicMock()
    free = MagicMock()
    free.scalar_one = MagicMock(return_value=0)
    db.execute = AsyncMock(return_value=free)
    db.add = MagicMock()
    suggestion = MagicMock()
    suggestion.url = "https://www.example-canon.org/read"
    suggestion.name = "示例藏经"
    suggestion.description = "推荐理由"

    await _create_data_source(db, suggestion)

    rows = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], DataSource)]
    assert len(rows) == 1
    assert rows[0].code == "example-canon"
    assert rows[0].is_active is False
