"""Tests for scripts/baidu_push.py — Baidu 主动推送 URL collection + CLI.

fojin.app gets ~70% mainland-China traffic but zero real Baiduspider crawls
in 30 days of prod logs, so this script pushes URLs to Baidu's active-push
API instead of waiting for an organic crawl. Coverage here:

* URL collection — the per-kind collectors build the same URL shapes
  app.api.sitemap serves, and apply the same junk-headword / entity-type
  filters (test_dict_urls_*, test_person_urls_*).
* --limit budget truncation, including across --kind all, where a small
  budget must never touch a collector once it's already full
  (test_all_fills_budget_..., test_single_kind_only_calls_its_own_collector).
* --dry-run never calls the network (test_dry_run_*).
* Missing BAIDU_PUSH_TOKEN fails fast, before any DB/network work
  (test_missing_token_*).
* The actual HTTP request shape sent to Baidu — mocked; these tests never
  hit the real API (test_push_urls_sends_expected_request_shape).
"""

from unittest.mock import AsyncMock
from urllib.parse import quote

import pytest
import pytest_asyncio
from scripts import baidu_push
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.dictionary import DictionaryEntry
from app.models.knowledge_graph import KGEntity


@pytest.fixture(autouse=True)
def _no_real_endpoint_check(monkeypatch):
    """main() handshakes with Baidu before sending the token; never in tests."""
    monkeypatch.setattr(baidu_push, "verify_push_endpoint", lambda *a, **k: None)


def _fake_collector(prefix: str, available: int):
    """An AsyncMock collector that, like the real ones, never returns more
    than the `limit` it's called with."""

    async def _collect(session, limit):
        n = min(available, limit)
        return [f"{prefix}-{i}" for i in range(n)]

    return AsyncMock(side_effect=_collect)


@pytest.fixture
def fake_collectors(monkeypatch):
    fakes = {
        "texts": _fake_collector("text", 5),
        "persons": _fake_collector("person", 5),
        "dict": _fake_collector("dict", 5),
    }
    for kind, fake in fakes.items():
        monkeypatch.setitem(baidu_push._COLLECTORS, kind, fake)
    return fakes


# ---------------------------------------------------------------------------
# collect_urls: kind dispatch + limit budgeting
# ---------------------------------------------------------------------------


async def test_single_kind_only_calls_its_own_collector(fake_collectors):
    urls = await baidu_push.collect_urls(session=None, kind="texts", limit=10)

    assert urls == ["text-0", "text-1", "text-2", "text-3", "text-4"]
    fake_collectors["texts"].assert_awaited_once_with(None, 10)
    fake_collectors["persons"].assert_not_called()
    fake_collectors["dict"].assert_not_called()


async def test_limit_truncates_a_single_kind(fake_collectors):
    urls = await baidu_push.collect_urls(session=None, kind="dict", limit=2)

    assert urls == ["dict-0", "dict-1"]
    fake_collectors["dict"].assert_awaited_once_with(None, 2)


async def test_all_fills_budget_in_order_and_skips_once_full(fake_collectors):
    # texts has 5 available: an 8-URL budget takes all 5, leaves 3 for
    # persons, and dict — last in line — should never even be called once
    # the budget is already spent on the first two.
    urls = await baidu_push.collect_urls(session=None, kind="all", limit=8)

    assert urls == [
        "text-0",
        "text-1",
        "text-2",
        "text-3",
        "text-4",
        "person-0",
        "person-1",
        "person-2",
    ]
    fake_collectors["texts"].assert_awaited_once_with(None, 8)
    fake_collectors["persons"].assert_awaited_once_with(None, 3)
    fake_collectors["dict"].assert_not_called()


async def test_all_with_limit_smaller_than_first_kind_never_touches_the_rest(fake_collectors):
    urls = await baidu_push.collect_urls(session=None, kind="all", limit=3)

    assert urls == ["text-0", "text-1", "text-2"]
    fake_collectors["texts"].assert_awaited_once_with(None, 3)
    fake_collectors["persons"].assert_not_called()
    fake_collectors["dict"].assert_not_called()


async def test_all_under_total_available_calls_every_kind(fake_collectors):
    # 5 + 5 + 5 = 15 available; a 12-URL budget must reach all three kinds.
    urls = await baidu_push.collect_urls(session=None, kind="all", limit=12)

    assert len(urls) == 12
    fake_collectors["texts"].assert_awaited_once_with(None, 12)
    fake_collectors["persons"].assert_awaited_once_with(None, 7)
    fake_collectors["dict"].assert_awaited_once_with(None, 2)


# ---------------------------------------------------------------------------
# Real collectors against an in-memory DB — URL shape + filtering
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def dict_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(DictionaryEntry.__table__.create)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


async def test_dict_urls_skips_junk_headwords_and_encodes_the_rest(dict_db):
    good = ["空", "般若"]
    junk = ["", "x" * 201, "bad\nword", "bad\tword"]
    for i, hw in enumerate(good + junk):
        dict_db.add(DictionaryEntry(headword=hw, source_id=1, lang="zh", external_id=f"e{i}"))
    await dict_db.commit()

    urls = await baidu_push._dict_urls(dict_db, limit=10)

    assert set(urls) == {f"{baidu_push.BASE_URL}/dict/{quote(hw, safe='')}" for hw in good}


async def test_dict_urls_respects_limit(dict_db):
    for i, hw in enumerate(["空", "般若", "涅槃"]):
        dict_db.add(DictionaryEntry(headword=hw, source_id=1, lang="zh", external_id=f"e{i}"))
    await dict_db.commit()

    urls = await baidu_push._dict_urls(dict_db, limit=2)

    assert len(urls) == 2


async def test_dict_urls_limit_zero_returns_empty_without_querying(dict_db):
    dict_db.add(DictionaryEntry(headword="空", source_id=1, lang="zh", external_id="e1"))
    await dict_db.commit()

    assert await baidu_push._dict_urls(dict_db, limit=0) == []


@pytest_asyncio.fixture
async def kg_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(KGEntity.__table__.create)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


async def test_person_urls_only_includes_person_entities(kg_db):
    kg_db.add(KGEntity(id=1, entity_type="person", name_zh="慧能"))
    kg_db.add(KGEntity(id=2, entity_type="place", name_zh="灵鹫山"))
    kg_db.add(KGEntity(id=3, entity_type="person", name_zh="鸠摩罗什"))
    await kg_db.commit()

    urls = await baidu_push._person_urls(kg_db, limit=10)

    assert set(urls) == {f"{baidu_push.BASE_URL}/persons/1", f"{baidu_push.BASE_URL}/persons/3"}


# ---------------------------------------------------------------------------
# push_urls: the actual HTTP request shape (httpx mocked — never hits Baidu)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.is_client_error = 400 <= status < 500

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise baidu_push.httpx.HTTPStatusError("boom", request=None, response=None)


class _FakeAsyncClient:
    """Records the single POST call made by push_urls; no real network."""

    response: _FakeResponse
    last_instance: "_FakeAsyncClient | None" = None

    def __init__(self, *args, **kwargs):
        self.post_calls: list[tuple] = []
        _FakeAsyncClient.last_instance = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return _FakeAsyncClient.response


async def test_push_urls_sends_expected_request_shape(monkeypatch):
    _FakeAsyncClient.response = _FakeResponse({"success": 2, "remain": 98})
    monkeypatch.setattr(baidu_push.httpx, "AsyncClient", _FakeAsyncClient)

    result = await baidu_push.push_urls(["https://fojin.app/texts/1", "https://fojin.app/texts/2"], "tok123")

    assert result == {"success": 2, "remain": 98}
    client = _FakeAsyncClient.last_instance
    assert client is not None
    assert len(client.post_calls) == 1
    url, kwargs = client.post_calls[0]
    # site must go out un-encoded: Baidu 400s on site=https%3A%2F%2Ffojin.app
    assert url == f"{baidu_push.PUSH_API_URL}?site=https://fojin.app&token=tok123"
    assert "params" not in kwargs
    assert kwargs["content"] == "https://fojin.app/texts/1\nhttps://fojin.app/texts/2"
    assert kwargs["headers"] == {"Content-Type": "text/plain"}


async def test_push_urls_returns_baidus_reason_on_4xx(monkeypatch):
    _FakeAsyncClient.response = _FakeResponse({"error": 400, "message": "over quota"}, status=400)
    monkeypatch.setattr(baidu_push.httpx, "AsyncClient", _FakeAsyncClient)

    result = await baidu_push.push_urls(["https://fojin.app/texts/1"], "tok123")

    assert result == {"error": 400, "message": "over quota"}


# ---------------------------------------------------------------------------
# main(): CLI orchestration — dry-run, missing token, success/error reporting
# ---------------------------------------------------------------------------


async def test_dry_run_prints_urls_and_never_calls_push(monkeypatch, capsys):
    monkeypatch.setattr(settings, "baidu_push_token", "test-token")
    monkeypatch.setattr(
        baidu_push,
        "collect_urls",
        AsyncMock(return_value=["https://fojin.app/texts/1", "https://fojin.app/texts/2"]),
    )
    push_mock = AsyncMock()
    monkeypatch.setattr(baidu_push, "push_urls", push_mock)

    rc = await baidu_push.main(["--dry-run", "--kind", "texts"])

    assert rc == 0
    push_mock.assert_not_called()
    out = capsys.readouterr().out
    assert "https://fojin.app/texts/1" in out
    assert "https://fojin.app/texts/2" in out


async def test_missing_token_errors_without_collecting_or_pushing(monkeypatch, capsys):
    monkeypatch.setattr(settings, "baidu_push_token", "")
    collect_mock = AsyncMock()
    monkeypatch.setattr(baidu_push, "collect_urls", collect_mock)
    push_mock = AsyncMock()
    monkeypatch.setattr(baidu_push, "push_urls", push_mock)

    rc = await baidu_push.main([])

    assert rc == 1
    collect_mock.assert_not_called()
    push_mock.assert_not_called()
    assert "BAIDU_PUSH_TOKEN" in capsys.readouterr().err


async def test_missing_token_errors_even_in_dry_run(monkeypatch, capsys):
    # --dry-run rehearses the real run's config too, so a cron job with a
    # forgotten token fails loudly in dry-run rather than looking fine.
    monkeypatch.setattr(settings, "baidu_push_token", "")

    rc = await baidu_push.main(["--dry-run"])

    assert rc == 1
    assert "BAIDU_PUSH_TOKEN" in capsys.readouterr().err


async def test_limit_below_one_is_rejected(capsys):
    rc = await baidu_push.main(["--limit", "0"])

    assert rc == 1
    assert "--limit" in capsys.readouterr().err


async def test_successful_run_prints_success_and_remain(monkeypatch, capsys):
    monkeypatch.setattr(settings, "baidu_push_token", "tok")
    monkeypatch.setattr(baidu_push, "collect_urls", AsyncMock(return_value=["https://fojin.app/texts/1"]))
    monkeypatch.setattr(baidu_push, "push_urls", AsyncMock(return_value={"success": 1, "remain": 99}))

    rc = await baidu_push.main(["--kind", "texts", "--limit", "1"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "success=1" in out
    assert "remain=99" in out


async def test_error_response_from_baidu_is_surfaced_as_failure(monkeypatch, capsys):
    monkeypatch.setattr(settings, "baidu_push_token", "tok")
    monkeypatch.setattr(baidu_push, "collect_urls", AsyncMock(return_value=["https://fojin.app/texts/1"]))
    monkeypatch.setattr(baidu_push, "push_urls", AsyncMock(return_value={"error": 401, "message": "token is invalid"}))

    rc = await baidu_push.main(["--kind", "texts"])

    assert rc == 1
    assert "token is invalid" in capsys.readouterr().err


async def test_empty_result_set_is_not_an_error(monkeypatch, capsys):
    monkeypatch.setattr(settings, "baidu_push_token", "tok")
    monkeypatch.setattr(baidu_push, "collect_urls", AsyncMock(return_value=[]))
    push_mock = AsyncMock()
    monkeypatch.setattr(baidu_push, "push_urls", push_mock)

    rc = await baidu_push.main(["--kind", "texts"])

    assert rc == 0
    push_mock.assert_not_called()


# ---------------------------------------------------------------------------
# 2026-10-19: https + identity pin, token never in logs, token via stdin, cursor
# ---------------------------------------------------------------------------


def test_endpoint_is_https():
    assert baidu_push.PUSH_API_URL.startswith("https://")


def test_cert_pin_rejects_a_verified_cert_that_is_not_baidus():
    import ssl

    good = {
        "subject": ((("organizationName", baidu_push._EXPECTED_ORG),),),
        "subjectAltName": (("DNS", "*.baidu.com"),),
    }
    baidu_push._check_baidu_cert(good)
    for bad in (
        {**good, "subject": ((("organizationName", "Evil Inc"),),)},
        {**good, "subjectAltName": (("DNS", "*.evil.com"),)},
    ):
        with pytest.raises(ssl.SSLError):
            baidu_push._check_baidu_cert(bad)


async def test_endpoint_check_failure_never_sends_the_token(monkeypatch, capsys):
    import ssl

    def _boom(*a, **k):
        raise ssl.SSLError("unexpected certificate")

    monkeypatch.setattr(baidu_push, "verify_push_endpoint", _boom)
    monkeypatch.setattr(settings, "baidu_push_token", "tok")
    monkeypatch.setattr(baidu_push, "collect_urls", AsyncMock(return_value=["https://fojin.app/texts/1"]))
    push_mock = AsyncMock()
    monkeypatch.setattr(baidu_push, "push_urls", push_mock)

    rc = await baidu_push.main(["--kind", "texts"])

    assert rc == 1
    push_mock.assert_not_called()
    assert "refusing to send the token" in capsys.readouterr().err


async def test_transport_error_never_prints_the_token(monkeypatch, capsys):
    secret = "SeCrEt1234567890"
    monkeypatch.setattr(settings, "baidu_push_token", secret)
    monkeypatch.setattr(baidu_push, "collect_urls", AsyncMock(return_value=["https://fojin.app/texts/1"]))
    err = baidu_push.httpx.ConnectError(f"failed: https://data.zz.baidu.com/urls?site=x&token={secret}")
    monkeypatch.setattr(baidu_push, "push_urls", AsyncMock(side_effect=err))

    rc = await baidu_push.main(["--kind", "texts"])

    captured = capsys.readouterr()
    assert rc == 1
    assert secret not in captured.err + captured.out
    assert "***" in captured.err


async def test_token_is_read_from_stdin_and_overrides_env(monkeypatch):
    import io

    monkeypatch.setattr(settings, "baidu_push_token", "")
    monkeypatch.setattr(baidu_push.sys, "stdin", io.StringIO("fromstdin\n"))
    monkeypatch.setattr(baidu_push, "collect_urls", AsyncMock(return_value=["https://fojin.app/texts/1"]))
    push_mock = AsyncMock(return_value={"success": 1, "remain": 9})
    monkeypatch.setattr(baidu_push, "push_urls", push_mock)

    rc = await baidu_push.main(["--kind", "texts", "--token-stdin"])

    assert rc == 0
    assert push_mock.await_args.args[1] == "fromstdin"


def _offset_collector(prefix: str, available: int):
    async def _collect(session, limit, offset=0):
        return [f"{prefix}-{i}" for i in range(offset, min(available, offset + limit))]

    return AsyncMock(side_effect=_collect)


@pytest.fixture
def offset_collectors(monkeypatch):
    for kind, n in (("texts", 5), ("persons", 3), ("dict", 4)):
        monkeypatch.setitem(baidu_push._COLLECTORS, kind, _offset_collector(kind, n))


async def test_cursor_continues_across_runs_and_kinds(offset_collectors):
    urls, off = await baidu_push.collect_with_cursor(None, "all", 4, {})
    assert urls == ["texts-0", "texts-1", "texts-2", "texts-3"]
    urls, off = await baidu_push.collect_with_cursor(None, "all", 4, off)
    # texts runs out after one more, the rest of the budget moves on to persons
    assert urls == ["texts-4", "persons-0", "persons-1", "persons-2"]
    urls, off = await baidu_push.collect_with_cursor(None, "all", 4, off)
    assert urls == ["dict-0", "dict-1", "dict-2", "dict-3"]


async def test_cursor_wraps_to_start_once_everything_was_pushed(offset_collectors):
    done = {"texts": 5, "persons": 3, "dict": 4}
    urls, off = await baidu_push.collect_with_cursor(None, "all", 2, done)
    assert urls == ["texts-0", "texts-1"]
    assert off["texts"] == 2


async def test_state_saved_only_after_baidu_accepts(monkeypatch, tmp_path):
    state = tmp_path / "state.json"
    monkeypatch.setattr(settings, "baidu_push_token", "tok")
    monkeypatch.setattr(
        baidu_push, "collect_with_cursor", AsyncMock(return_value=(["https://fojin.app/texts/1"], {"texts": 1}))
    )
    monkeypatch.setattr(baidu_push, "push_urls", AsyncMock(return_value={"error": 400, "message": "over quota"}))
    assert await baidu_push.main(["--kind", "texts", "--state-file", str(state)]) == 1
    assert not state.exists()

    monkeypatch.setattr(baidu_push, "push_urls", AsyncMock(return_value={"success": 1, "remain": 9}))
    assert await baidu_push.main(["--kind", "texts", "--state-file", str(state)]) == 0
    assert baidu_push.load_state(str(state)) == {"texts": 1}
