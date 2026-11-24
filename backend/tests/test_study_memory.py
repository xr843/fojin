"""研读记忆：真库（SQLite）算记忆 + 接口往返 + 交给模型的格式 + 迁移与 ORM 一致。"""

import importlib.util
import pathlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.deps import get_current_user
from app.database import get_db
from app.main import app
from app.models.chat import ChatMessage, ChatSession
from app.models.excerpt import UserExcerpt
from app.models.source import DataSource
from app.models.study_memory import UserStudyMemory
from app.models.text import BuddhistText
from app.models.user import ReadingHistory, User
from app.services.prompt_builder import _build_llm_messages
from app.services.study_memory import (
    StudyMemory,
    TopicItem,
    build_study_memory,
    render_memory_block,
)

# 用真实当前时间：接口内部按 now() 算 30 天窗口，写死日期的测试过一个月就会坏。
NOW = datetime.now(UTC)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for model in (User, DataSource, BuddhistText, ReadingHistory, ChatSession, ChatMessage, UserExcerpt,
                      UserStudyMemory):
            await conn.run_sync(model.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        s.add_all([
            BuddhistText(id=1, cbeta_id="T1558", title_zh="阿毘達磨俱舍論", has_content=True),
            BuddhistText(id=2, cbeta_id="T1585", title_zh="成唯識論", has_content=True),
            BuddhistText(id=3, cbeta_id="T0235", title_zh="金剛般若波羅蜜經", has_content=True),
        ])
        d = lambda n: NOW - timedelta(days=n)  # noqa: E731
        s.add_all([
            ReadingHistory(user_id=1, text_id=1, juan_num=6, last_read_at=d(2)),
            ReadingHistory(user_id=1, text_id=2, juan_num=2, last_read_at=d(0)),
            ReadingHistory(user_id=1, text_id=3, juan_num=1, last_read_at=d(45)),  # 窗口外
            ReadingHistory(user_id=2, text_id=3, juan_num=1, last_read_at=d(1)),  # 别人的
        ])
        s.add_all([
            ChatSession(id=10, user_id=1, title="种子与习气的关系"),
            ChatSession(id=11, user_id=1, title="俱舍论 思所作"),
            ChatSession(id=12, user_id=1, title="种子与习气的关系"),  # 同名，去重
            ChatSession(id=13, user_id=1, title="很久以前的话题"),
            ChatSession(id=14, user_id=2, title="别人的话题"),
        ])
        s.add_all([
            ChatMessage(session_id=10, role="user", content="q", created_at=d(1)),
            ChatMessage(session_id=11, role="user", content="q", created_at=d(3)),
            ChatMessage(session_id=12, role="user", content="q", created_at=d(4)),
            ChatMessage(session_id=13, role="user", content="q", created_at=d(60)),
            ChatMessage(session_id=14, role="user", content="q", created_at=d(1)),
        ])
        s.add(UserExcerpt(user_id=1, text_id=1, juan_num=6, quote="思所作業" * 20, created_at=d(2)))
        await s.commit()
        yield s
    await engine.dispose()


@pytest.mark.anyio
async def test_build_only_recent_own_records(db):
    mem = await build_study_memory(db, 1, now=NOW)
    assert [(r.title_zh, r.juan_num) for r in mem.reading] == [("成唯識論", 2), ("阿毘達磨俱舍論", 6)]
    assert [t.title for t in mem.topics] == ["种子与习气的关系", "俱舍论 思所作"]
    assert len(mem.excerpts) == 1 and mem.excerpts[0].quote.endswith("…")
    assert len(mem.excerpts[0].quote) == 41


@pytest.mark.anyio
async def test_current_session_is_not_its_own_topic(db):
    mem = await build_study_memory(db, 1, exclude_session_id=10, now=NOW)
    # 10 号被排除后，同名的 12 号补上
    assert [t.session_id for t in mem.topics] == [11, 12]


@pytest.mark.anyio
async def test_disabled_returns_no_records(db):
    db.add(UserStudyMemory(user_id=1, enabled=False, notes="用繁体"))
    await db.commit()
    mem = await build_study_memory(db, 1, now=NOW)
    assert not mem.enabled and mem.reading == [] and mem.topics == [] and mem.excerpts == []
    assert render_memory_block(mem, now=NOW) == ""


def test_render_block_rules_and_content():
    mem = StudyMemory(notes="我在学唯识，请对照述记", topics=[TopicItem(1, "种子", NOW)])
    block = render_memory_block(mem, now=NOW)
    assert block.startswith("【读者研读背景】") and block.rstrip().endswith("【背景结束】")
    assert "不得作为引文出处或论据" in block
    assert "「种子」" in block and "「我在学唯识，请对照述记」" in block
    assert render_memory_block(StudyMemory(), now=NOW) == ""


def test_memory_rides_in_user_turn_and_system_prompt_is_unchanged():
    block = render_memory_block(StudyMemory(notes="用繁体"), now=NOW)
    plain = _build_llm_messages([], "【片段】如是我聞", "什么是种子？")
    with_mem = _build_llm_messages([], "【片段】如是我聞", "什么是种子？", memory_block=block)
    assert with_mem[0] == plain[0]  # 系统提示词一字不动
    assert with_mem[-1]["content"] == block + plain[-1]["content"]
    no_ctx = _build_llm_messages([], "", "你好", memory_block=block)
    assert no_ctx[-1]["content"] == block + "你好"


def _client(db, user_id):
    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=user_id)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.anyio
async def test_api_roundtrip_and_isolation(db):
    async with _client(db, 1) as c:
        r = await c.get("/api/study-memory")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["enabled"] is True and body["notes"] is None and body["max_notes_chars"] == 300
        assert body["used_in_answers"] is True
        assert [r["title_zh"] for r in body["reading"]] == ["成唯識論", "阿毘達磨俱舍論"]

        r = await c.put("/api/study-memory", json={"enabled": True, "notes": "  我在学唯识\n请对照述记  "})
        assert r.json()["notes"] == "我在学唯识 请对照述记"

        r = await c.put("/api/study-memory", json={"enabled": False, "notes": "x"})
        assert r.json()["enabled"] is False and r.json()["reading"] == [] and r.json()["topics"] == []

        assert (await c.put("/api/study-memory", json={"enabled": True, "notes": "字" * 301})).status_code == 422
    async with _client(db, 2) as c:
        body = (await c.get("/api/study-memory")).json()
        assert body["enabled"] is True and body["notes"] is None
        assert [t["title"] for t in body["topics"]] == ["别人的话题"]


def test_migration_columns_match_orm():
    """迁移建的列必须和 ORM 一模一样——门禁里没有真库往返，错配只会在生产炸。"""
    path = next(pathlib.Path(__file__).parents[1].glob("alembic/versions/0192_user_study_memory_*.py"))
    spec = importlib.util.spec_from_file_location("m0192", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    created = {}

    class FakeOp:
        def create_table(self, name, *cols):
            created[name] = {c.name: c for c in cols}

    mod.op = FakeOp()
    mod.upgrade()
    mig = created["user_study_memory"]
    orm = UserStudyMemory.__table__.columns
    assert set(mig) == {c.name for c in orm}
    for c in orm:
        assert mig[c.name].nullable == c.nullable, c.name
        assert type(mig[c.name].type).__name__ == type(c.type).__name__, c.name


def test_memory_switch(monkeypatch):
    from app.services import chat
    from app.services.chat import _memory_applies

    assert chat.settings.study_memory_inject is True  # 评测过关后默认开
    monkeypatch.setattr(chat.settings, "study_memory_inject", False)
    assert not _memory_applies(1, None, None, "什么是种子？")  # 回滚开关有效


def test_memory_only_on_the_plain_qa_path(monkeypatch):
    from app.services import chat
    from app.services.chat import _memory_applies

    # 改 chat 模块手里那份 settings：别的测试会重载 app.config，全局对象可能已不是同一个
    monkeypatch.setattr(chat.settings, "study_memory_inject", True)
    assert _memory_applies(1, None, None, "什么是种子？")
    assert not _memory_applies(None, None, None, "什么是种子？")  # 游客
    assert not _memory_applies(1, "xuanzang", None, "什么是种子？")  # 祖师
    assert not _memory_applies(1, None, {"title": "成唯識論"}, "什么是种子？")  # 阅读页
    assert not _memory_applies(1, None, None, "你是谁")  # 元问题
