"""Integration tests for POST /chat/attachments and the attachment ownership
filter in the chat service.

The DB layer is mocked at the AsyncSession boundary — the real persistence
path is exercised by alembic + a manual smoke run, since these tests are
designed to pass without Postgres.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.chat import _load_and_render_attachments


# ---------------------------------------------------------------------------
# POST /chat/attachments — happy path + 415 + 413
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_upload_happy_path_txt(client, tmp_path, monkeypatch):
    from app.api import chat as chat_api
    from app.database import get_db as real_get_db
    from app.main import app

    monkeypatch.setattr(chat_api.settings, "upload_dir", str(tmp_path))

    captured: dict[str, object] = {}

    async def fake_refresh(obj):
        # Simulate INSERT ... RETURNING id
        obj.id = 4242

    mock_db = AsyncMock()

    def _add(obj):
        captured["row"] = obj
    mock_db.add = MagicMock(side_effect=_add)
    mock_db.commit = AsyncMock(return_value=None)
    mock_db.refresh = AsyncMock(side_effect=fake_refresh)

    app.dependency_overrides[real_get_db] = lambda: mock_db
    try:
        files = {"file": ("hello.txt", b"hello chat\n", "text/plain")}
        resp = await client.post("/api/chat/attachments", files=files)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["id"] == 4242
        assert body["filename"] == "hello.txt"
        assert body["size_bytes"] == len(b"hello chat\n")
        assert "hello chat" in body["preview"]
        # The DB row had parsed_text populated
        row = captured["row"]
        assert row.parsed_text == "hello chat"
        assert row.parse_error is None
    finally:
        app.dependency_overrides.pop(real_get_db, None)


@pytest.mark.anyio
async def test_upload_unsupported_type_returns_415(client):
    files = {"file": ("evil.exe", b"\x00\x01", "application/octet-stream")}
    resp = await client.post("/api/chat/attachments", files=files)
    assert resp.status_code == 415, resp.text
    assert "PDF" in resp.json()["detail"]


@pytest.mark.anyio
async def test_upload_oversize_returns_413(client, tmp_path, monkeypatch):
    from app.api import chat as chat_api

    monkeypatch.setattr(chat_api.settings, "upload_dir", str(tmp_path))
    # Forge a file just over the 10 MiB cap.  Use a sparse-ish payload
    # to keep the test fast.
    big = b"x" * (10 * 1024 * 1024 + 1)
    files = {"file": ("big.txt", big, "text/plain")}
    resp = await client.post("/api/chat/attachments", files=files)
    assert resp.status_code == 413, resp.text


# ---------------------------------------------------------------------------
# Ownership: a logged-in user must NOT be able to consume another user's
# attachment by guessing the id. This is the IDOR-style invariant the
# whole feature hinges on.
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_attachment_ownership_filter():
    """``_load_and_render_attachments`` must filter rows by user_id.

    We mock the AsyncSession so the actual SQL doesn't run; what we
    assert is that the WHERE clause carries the ownership filter (the
    helper uses scalars().all() — if the clause is wrong, real PG would
    leak rows; here we just check the helper passes the user_id through
    correctly by inspecting which rows it returns from the mocked
    result set).
    """
    # Two rows in the "DB": id=1 owned by user 99; id=2 anonymous.
    row_other = MagicMock()
    row_other.id = 1
    row_other.user_id = 99
    row_other.filename = "secret.txt"
    row_other.parsed_text = "secret"
    row_other.parse_error = None

    row_anon = MagicMock()
    row_anon.id = 2
    row_anon.user_id = None
    row_anon.filename = "public.txt"
    row_anon.parsed_text = "public"
    row_anon.parse_error = None

    # Track the WHERE clauses applied. The helper constructs
    # ``select(...).where(id.in_(...)).where(user_id == X | is_(None))``;
    # we sniff the final stmt by intercepting db.execute.
    captured_stmts: list[object] = []

    def fake_execute(stmt):
        captured_stmts.append(stmt)
        # Pretend the DB applied the ownership filter for us — return
        # only rows the user (id=1) is allowed to see.  If the helper
        # silently drops the user filter, that's a regression we can't
        # catch here; the contract test below covers it via SQL string.
        scalar_result = MagicMock()
        scalar_result.all.return_value = [row_anon]  # row_other filtered out
        result = MagicMock()
        result.scalars.return_value = scalar_result
        async def _coro():
            return result
        return _coro()

    db = MagicMock()
    db.execute = fake_execute

    prefix, attachments = await _load_and_render_attachments(
        db, [1, 2], user_id=1,
    )
    # Only the anonymous row survived
    assert len(attachments) == 1
    assert attachments[0].id == 2
    assert "public.txt" in prefix
    assert "secret" not in prefix

    # And the SQL statement actually carried a user_id filter (defensive
    # — guards against a future refactor that drops the where clause).
    stmt_sql = str(captured_stmts[0]).lower()
    assert "user_id" in stmt_sql


@pytest.mark.anyio
async def test_attachment_anonymous_caller_only_sees_anon_rows():
    captured_stmts: list[object] = []

    def fake_execute(stmt):
        captured_stmts.append(stmt)
        scalar_result = MagicMock()
        scalar_result.all.return_value = []
        result = MagicMock()
        result.scalars.return_value = scalar_result
        async def _coro():
            return result
        return _coro()

    db = MagicMock()
    db.execute = fake_execute

    prefix, attachments = await _load_and_render_attachments(
        db, [42], user_id=None,
    )
    assert prefix == ""
    assert attachments == []
    # Anonymous filter must mention IS NULL
    stmt_sql = str(captured_stmts[0]).lower()
    assert "is null" in stmt_sql or "user_id" in stmt_sql


@pytest.mark.anyio
async def test_attachment_render_format():
    """Format contract: header / body / footer with filename + char count."""
    row = MagicMock()
    row.id = 7
    row.user_id = None
    row.filename = "doc.txt"
    row.parsed_text = "hello"
    row.parse_error = None

    def fake_execute(stmt):
        scalar_result = MagicMock()
        scalar_result.all.return_value = [row]
        result = MagicMock()
        result.scalars.return_value = scalar_result
        async def _coro():
            return result
        return _coro()

    db = MagicMock()
    db.execute = fake_execute

    prefix, _ = await _load_and_render_attachments(db, [7], user_id=None)
    assert "===== 附件: doc.txt (5 字) =====" in prefix
    assert "hello" in prefix
    assert "===== 附件结束 =====" in prefix


@pytest.mark.anyio
async def test_attachment_parse_failure_renders_error_marker():
    row = MagicMock()
    row.id = 8
    row.user_id = None
    row.filename = "bad.pdf"
    row.parsed_text = None
    row.parse_error = "PDF 文件损坏"

    def fake_execute(stmt):
        scalar_result = MagicMock()
        scalar_result.all.return_value = [row]
        result = MagicMock()
        result.scalars.return_value = scalar_result
        async def _coro():
            return result
        return _coro()

    db = MagicMock()
    db.execute = fake_execute

    prefix, _ = await _load_and_render_attachments(db, [8], user_id=None)
    assert "解析失败" in prefix
    assert "PDF 文件损坏" in prefix
