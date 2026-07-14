# 管理后台优化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把差答案队列的判据从「有没有引经」改成「引用是否可核对」,并把后台常驻菜单从 8 项收敛到 4 项、给隐藏的候选对齐复核页补上入口。

**Architecture:** 队列不再对 `chat_messages` 全表扫后在 Python 里打分,而是 INNER JOIN `chat_answer_diagnostics`(2026-07-01 落地),用 SQL 表达全部判据、排序、分页与计数。诊断表记录的是**入库前那一刻**的引用真相——这是唯一幸存的证据,因为 `verify_quoted_content` 会在保存前把对不上的引号剥掉。前端菜单按"有没有活儿"重排,角标走一条便宜的 COUNT 端点。

**Tech Stack:** FastAPI + SQLAlchemy 2.0(async)+ Pydantic v2;React + TypeScript + antd 5;pytest / vitest。

## Global Constraints

- **7/1 之前的消息不进队列**:靠 INNER JOIN 诊断表天然实现。不要为老消息补算——证据已被 `verify_quoted_content` 销毁,任何"重算"都会得出假的"一切正常"。
- **不改 `WEAK_EVIDENCE_THRESHOLD` 的数值**(保持 `0.37`)。本次只把**标签分布**吐出来,阈值等看到真实分布后另行调整。
- **角标必须便宜**:每次导航都会读它,只能用 `COUNT(*)`,禁止跑 Python 打分。
- 队列窗口默认值 `90` → `30`。
- 删除 `no_citation` 标签;新增 `fabricated_citation` / `quote_relaxed` / `citation_corrected`;保留 `downvoted` / `abnormal` / `weak_evidence`。
- 后端 commit 前跑 `cd backend && pytest tests/test_answer_quality.py tests/test_admin.py -q`;前端跑 `cd frontend && npx vitest run src/pages/AdminAnswerQualityPage.test.tsx src/pages/AdminCrudPages.test.tsx`。

---

# PR 1 — 后端:判据换血 + SQL 下推 + 角标端点

### Task 1: `classify_answer` 换判据(纯函数)

**Files:**
- Modify: `backend/app/services/answer_quality.py:12-107`
- Test: `backend/tests/test_answer_quality.py:30-70`

**Interfaces:**
- Consumes: `ChatAnswerDiagnostic` 的列(`backend/app/models/chat.py:53-75`)——但**不直接接收 ORM 对象**,而是一个纯数据结构,以保持函数可单测。
- Produces:
  ```python
  @dataclass(frozen=True)
  class DiagnosticSignals:
      citation_count: int
      source_count: int
      quote_mutation_count: int
      citation_mutation_count: int
      max_source_score: float | None

  def classify_answer(
      content: str | None, feedback: str | None, diag: DiagnosticSignals
  ) -> tuple[list[str], float]
  ```
  注意签名变了:**去掉 `sources` 参数**(打分不再需要它;`max_source_score` 从诊断行来),**新增 `diag`**。`sources` 仍用于展示(`_clean_sources`)。

- [ ] **Step 1: 写失败测试**

替换 `backend/tests/test_answer_quality.py` 里旧的纯函数测试(第 30-70 行那一组,含 `test_no_citation_is_flagged`),改成:

```python
from app.services.answer_quality import (
    DiagnosticSignals,
    WEAK_EVIDENCE_THRESHOLD,
    classify_answer,
)


def _diag(
    citation_count=1,
    source_count=3,
    quote_mutation_count=0,
    citation_mutation_count=0,
    max_source_score=0.9,
):
    return DiagnosticSignals(
        citation_count=citation_count,
        source_count=source_count,
        quote_mutation_count=quote_mutation_count,
        citation_mutation_count=citation_mutation_count,
        max_source_score=max_source_score,
    )


_OK_ANSWER = "一段足够长的正常回答内容" * 3


def test_strong_answer_is_not_suspect():
    tags, score = classify_answer(_OK_ANSWER, None, _diag())
    assert tags == []
    assert score == 0.0


def test_chitchat_without_sources_is_not_suspect():
    """本来就不需要引经的问题(闲聊/元问题):回答没引用、也没来源 —— 不再是差答案。
    这正是旧 no_citation 判据制造 715 条噪音的地方。"""
    tags, score = classify_answer(
        _OK_ANSWER, None, _diag(citation_count=0, source_count=0, max_source_score=None)
    )
    assert tags == []
    assert score == 0.0


def test_fabricated_citation_is_flagged():
    """回答引了经,却一条来源都没有 —— 凭空引用。"""
    tags, score = classify_answer(
        _OK_ANSWER, None, _diag(citation_count=2, source_count=0, max_source_score=None)
    )
    assert tags == ["fabricated_citation"]
    assert score == 4.0


def test_quote_relaxed_is_flagged():
    tags, score = classify_answer(_OK_ANSWER, None, _diag(quote_mutation_count=1))
    assert tags == ["quote_relaxed"]
    assert score == 3.0


def test_citation_corrected_is_flagged():
    tags, score = classify_answer(_OK_ANSWER, None, _diag(citation_mutation_count=2))
    assert tags == ["citation_corrected"]
    assert score == 2.0


def test_downvoted_is_flagged():
    tags, score = classify_answer(_OK_ANSWER, "down", _diag())
    assert tags == ["downvoted"]
    assert score == 5.0


def test_short_answer_is_flagged_as_abnormal():
    tags, score = classify_answer("不知道", None, _diag())
    assert tags == ["abnormal"]
    assert score == 3.0


def test_weak_evidence_is_flagged_and_graded():
    """梯度沿用生产原公式 1.0 + min(gap, 0.5) * 2.0(gap = 阈值 - 来源分)。
    注意 gap 最大只有 0.37,所以那个 0.5 的封顶永远够不着 —— 这是生产旧代码自带的
    死枝,本次不动它(改评分语义会让 Task 2 的 SQL 排序与页面显示的分数对不上)。"""
    near, score_near = classify_answer(
        _OK_ANSWER, None, _diag(max_source_score=WEAK_EVIDENCE_THRESHOLD - 0.01)
    )
    far, score_far = classify_answer(_OK_ANSWER, None, _diag(max_source_score=0.01))
    assert near == ["weak_evidence"] and far == ["weak_evidence"]
    assert score_near == 1.02   # 1.0 + 0.01 * 2
    assert score_far == 1.72    # 1.0 + 0.36 * 2


def test_multiple_detectors_stack():
    tags, score = classify_answer(
        "太短", "down", _diag(citation_count=1, source_count=0, quote_mutation_count=1)
    )
    assert set(tags) == {"downvoted", "abnormal", "fabricated_citation", "quote_relaxed"}
    assert score == 5.0 + 3.0 + 4.0 + 3.0


def test_no_citation_tag_is_gone():
    """旧判据已删除:任何输入都不该再产出 no_citation。"""
    tags, _ = classify_answer(
        _OK_ANSWER, None, _diag(citation_count=0, source_count=0, max_source_score=None)
    )
    assert "no_citation" not in tags
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && pytest tests/test_answer_quality.py -q`
Expected: FAIL — `ImportError: cannot import name 'DiagnosticSignals'`

- [ ] **Step 3: 实现**

在 `backend/app/services/answer_quality.py` 中,把 `WEIGHTS`(第 28-33 行)与 `classify_answer`(第 77-107 行)替换为:

```python
# reason tag -> base weight in the suspicion score.
#
# 判据是「引用是否可核对」,不是「有没有引经」。旧的 no_citation(= 无任何来源)
# 把闲聊/元问题("what can you do today?")和真实的引用失败混为一谈,制造了 715
# 条噪音、淹没了信号,已删除。
WEIGHTS = {
    "downvoted": 5.0,
    "fabricated_citation": 4.0,
    "quote_relaxed": 3.0,
    "abnormal": 3.0,
    "citation_corrected": 2.0,
    "weak_evidence": 1.0,  # plus a graded bonus, see classify_answer
}


@dataclass(frozen=True)
class DiagnosticSignals:
    """一条回答在 *入库前* 的引用真相,来自 chat_answer_diagnostics。

    必须从这张表读,不能对 chat_messages.content 重算:verify_quoted_content 的
    契约是「fojin 从不端出假的逐字引用」,对不上原文的引号在保存前就被剥掉了
    (quote_verifier.py:373-382),重算只会得到「一切正常」。"""

    citation_count: int
    source_count: int
    quote_mutation_count: int
    citation_mutation_count: int
    max_source_score: float | None


def classify_answer(
    content: str | None, feedback: str | None, diag: DiagnosticSignals
) -> tuple[list[str], float]:
    """Pure detector. 给定一条回答的列 + 它的诊断行,返回命中的标签与可疑度
    (0.0 = 不可疑)。失败/空回答在上游过滤,不在这里打分。"""
    tags: list[str] = []
    score = 0.0

    if feedback == "down":
        tags.append("downvoted")
        score += WEIGHTS["downvoted"]

    if len((content or "").strip()) < ABNORMAL_MIN_CHARS:
        tags.append("abnormal")
        score += WEIGHTS["abnormal"]

    # 引了经却零来源 = 凭空引用,最严重的可核对性失败。
    if diag.citation_count > 0 and diag.source_count == 0:
        tags.append("fabricated_citation")
        score += WEIGHTS["fabricated_citation"]

    # 系统把「转述当原文引」降级过 —— 用户看到的是修好的,但这条本来是错的。
    if diag.quote_mutation_count > 0:
        tags.append("quote_relaxed")
        score += WEIGHTS["quote_relaxed"]

    if diag.citation_mutation_count > 0:
        tags.append("citation_corrected")
        score += WEIGHTS["citation_corrected"]

    mss = diag.max_source_score
    if mss is not None and mss < WEAK_EVIDENCE_THRESHOLD:
        tags.append("weak_evidence")
        # graded: deeper below threshold => more suspect (bonus capped at 1.0)
        score += WEIGHTS["weak_evidence"] + min(WEAK_EVIDENCE_THRESHOLD - mss, 0.5) * 2.0

    return tags, round(score, 3)
```

同时把文件顶部的 import 补上 `dataclass` 已有(第 3 行 `from dataclasses import asdict, dataclass`),无需改动。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && pytest tests/test_answer_quality.py -q -k "classify or suspect or flagged or stack or chitchat or gone"`
Expected: PASS(队列相关的测试此时仍会失败,下一个 Task 修——本步只看纯函数这一组)

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/answer_quality.py backend/tests/test_answer_quality.py
git commit -m "feat(admin): 差答案判据改为引用可核对性,删除 no_citation"
```

---

### Task 2: 队列改为 SQL 下推(join 诊断表 + 排序/分页/计数)

**Files:**
- Modify: `backend/app/services/answer_quality.py:168-234`(`build_bad_answer_queue`)
- Test: `backend/tests/test_answer_quality.py`(队列那一组)

**Interfaces:**
- Consumes: Task 1 的 `DiagnosticSignals` / `classify_answer` / `WEIGHTS`。
- Produces:
  ```python
  async def build_bad_answer_queue(
      db, *, window_days: int = 30, min_suspicion: float = 0.0,
      category: str | None = None, limit: int = 50, offset: int = 0,
  ) -> dict   # {total_unreviewed, score_distribution, tag_distribution, items}

  async def count_unreviewed(db, *, window_days: int = 30) -> int   # 角标用,只跑 COUNT
  ```
  `tag_distribution` 是 `dict[str, int]`(标签 → 命中条数),供事后校准阈值。

- [ ] **Step 1: 写失败测试**

**先改已有的 fixture,别新造一个。** `backend/tests/test_answer_quality.py:152-161` 的 `aq_session` 是逐个建表(不是 `Base.metadata.create_all`),必须把新表加进去:

```python
from app.models.chat import ChatAnswerDiagnostic, ChatMessage, ChatSession  # 第 13 行,补 ChatAnswerDiagnostic


@pytest_asyncio.fixture
async def aq_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for model in (ChatSession, ChatMessage, AnswerReview, ChatAnswerDiagnostic):
            await conn.run_sync(model.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()
```

给已有的 `_seed_turn`(第 164 行)加一个 `diag` 参数——**`diag=None` 表示这条消息没有诊断行**(模拟 2026-07-01 之前的老消息):

```python
async def _seed_turn(s, *, question, answer, sources, feedback=None, diag: dict | None = None):
    """Insert a user question + assistant answer that share one created_at, the
    way the chat save path does (single transaction, equal server-side now()).

    ``diag=None`` = 没有诊断行 = 2026-07-01 之前的老消息(证据已被
    verify_quoted_content 在入库前抹平,不可追溯)。"""
    ts = datetime.now(UTC)
    session = ChatSession(user_id=None)
    s.add(session)
    await s.flush()
    s.add(
        ChatMessage(
            session_id=session.id, role="user", content=question, created_at=ts
        )
    )
    assistant = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=answer,
        sources=sources,
        feedback=feedback,
        created_at=ts,
    )
    s.add(assistant)
    await s.flush()
    if diag is not None:
        s.add(
            ChatAnswerDiagnostic(
                message_id=assistant.id, trust_state="verified", **diag
            )
        )
    await s.commit()
    return assistant.id


def _diag_row(
    citation_count=1,
    source_count=3,
    quote_mutation_count=0,
    citation_mutation_count=0,
    max_source_score=0.9,
):
    return dict(
        citation_count=citation_count,
        source_count=source_count,
        quote_mutation_count=quote_mutation_count,
        citation_mutation_count=citation_mutation_count,
        max_source_score=max_source_score,
    )
```

**注意:文件里已有的队列测试(如 `test_queue_pairs_question_on_equal_timestamp`,第 189 行起)调用 `_seed_turn` 时都没传 `diag`,新判据下它们会得到"无诊断行 → 不进队列",于是断言全部失败。**必须给这些已有用例补上 `diag=_diag_row(...)`,并按新判据调整它们的期望标签(旧的 `no_citation` 已不存在)。

然后追加新用例:

```python
@pytest.mark.anyio
async def test_message_without_diagnostic_never_enters_queue(aq_session):
    """7/1 之前的老消息没有诊断行 —— 证据已在入库时销毁,不可追溯,必须排除。
    即便它同时命中 downvoted + abnormal 也不能进队列。"""
    await _seed_turn(
        aq_session, question="q", answer="太短", sources=_sources(0.9),
        feedback="down", diag=None,
    )
    result = await build_bad_answer_queue(aq_session)
    assert result["total_unreviewed"] == 0
    assert result["items"] == []


@pytest.mark.anyio
async def test_clean_answer_with_diagnostic_is_not_queued(aq_session):
    await _seed_turn(
        aq_session, question="q", answer=_OK_ANSWER, sources=_sources(0.9),
        diag=_diag_row(),
    )
    result = await build_bad_answer_queue(aq_session)
    assert result["total_unreviewed"] == 0


@pytest.mark.anyio
async def test_chitchat_without_sources_is_not_queued(aq_session):
    """"what can you do today?" 这类问题:没引用、没来源 —— 不再是差答案。
    旧的 no_citation 判据正是在这里制造了 715 条噪音。"""
    await _seed_turn(
        aq_session, question="what can you do today?", answer=_OK_ANSWER, sources=None,
        diag=_diag_row(citation_count=0, source_count=0, max_source_score=None),
    )
    result = await build_bad_answer_queue(aq_session)
    assert result["total_unreviewed"] == 0


@pytest.mark.anyio
async def test_fabricated_citation_enters_queue_with_tag(aq_session):
    mid = await _seed_turn(
        aq_session, question="q", answer=_OK_ANSWER, sources=None,
        diag=_diag_row(citation_count=2, source_count=0, max_source_score=None),
    )
    result = await build_bad_answer_queue(aq_session)
    assert result["total_unreviewed"] == 1
    assert result["items"][0]["message_id"] == mid
    assert result["items"][0]["reason_tags"] == ["fabricated_citation"]
    assert result["tag_distribution"]["fabricated_citation"] == 1


@pytest.mark.anyio
async def test_queue_orders_by_suspicion_desc(aq_session):
    weak = await _seed_turn(
        aq_session, question="q1", answer=_OK_ANSWER, sources=_sources(0.30),
        diag=_diag_row(source_count=1, max_source_score=0.30),
    )  # weak_evidence ≈ 1.14
    downvoted = await _seed_turn(
        aq_session, question="q2", answer=_OK_ANSWER, sources=_sources(0.9),
        feedback="down", diag=_diag_row(),
    )  # 5.0
    result = await build_bad_answer_queue(aq_session)
    ids = [it["message_id"] for it in result["items"]]
    assert ids == [downvoted, weak]


@pytest.mark.anyio
async def test_limit_offset_pushed_down_and_total_consistent(aq_session):
    for i in range(3):
        await _seed_turn(
            aq_session, question=f"q{i}", answer=_OK_ANSWER, sources=None,
            diag=_diag_row(citation_count=1, source_count=0, max_source_score=None),
        )
    page = await build_bad_answer_queue(aq_session, limit=2, offset=0)
    assert page["total_unreviewed"] == 3      # total 是全量,不是本页
    assert len(page["items"]) == 2            # 本页只有 2 条
    tail = await build_bad_answer_queue(aq_session, limit=2, offset=2)
    assert len(tail["items"]) == 1


@pytest.mark.anyio
async def test_count_unreviewed_matches_queue_total(aq_session):
    await _seed_turn(
        aq_session, question="q", answer=_OK_ANSWER, sources=None,
        diag=_diag_row(citation_count=1, source_count=0, max_source_score=None),
    )
    assert await count_unreviewed(aq_session) == 1
```

在文件顶部的 import 中加入 `count_unreviewed`。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && pytest tests/test_answer_quality.py -q -k "queue or count_unreviewed or diagnostic"`
Expected: FAIL — `ImportError: cannot import name 'count_unreviewed'`

- [ ] **Step 3: 实现**

把 `backend/app/services/answer_quality.py` 里的 `build_bad_answer_queue`(第 168-234 行)整体替换,并新增两个 SQL 表达式辅助与 `count_unreviewed`。文件顶部 import 改为:

```python
from sqlalchemy import and_, case, func, or_, select
from app.models.chat import ChatAnswerDiagnostic, ChatMessage
```

新增(放在 `classify_answer` 之后):

```python
# --- SQL 侧判据 ------------------------------------------------------------
# 与 classify_answer 一一对应。判据全部是诊断表上的列比较,所以排序、分页、计数
# 都能下推到 SQL —— 旧实现把窗口内每条 assistant 消息连同完整 sources JSON 拉进
# Python 再内存分页(实测 1.8s / 80KB,随流量线性劣化)。

_M = ChatMessage
_D = ChatAnswerDiagnostic

TAG_PREDICATES = {
    "downvoted": _M.feedback == "down",
    "abnormal": func.length(func.trim(_M.content)) < ABNORMAL_MIN_CHARS,
    "fabricated_citation": and_(_D.citation_count > 0, _D.source_count == 0),
    "quote_relaxed": _D.quote_mutation_count > 0,
    "citation_corrected": _D.citation_mutation_count > 0,
    "weak_evidence": and_(
        _D.max_source_score.is_not(None),
        _D.max_source_score < WEAK_EVIDENCE_THRESHOLD,
    ),
}


def _score_expr():
    """SQL 版可疑度,与 classify_answer 的算法逐项对齐。梯度用 case 表达(而非
    LEAST/MIN —— 那两个在 sqlite 与 postgres 上名字不同),保证可移植。"""
    gap = WEAK_EVIDENCE_THRESHOLD - _D.max_source_score
    graded = case((gap > 0.5, 1.0), else_=gap * 2.0)
    return (
        case((TAG_PREDICATES["downvoted"], WEIGHTS["downvoted"]), else_=0.0)
        + case((TAG_PREDICATES["abnormal"], WEIGHTS["abnormal"]), else_=0.0)
        + case(
            (TAG_PREDICATES["fabricated_citation"], WEIGHTS["fabricated_citation"]),
            else_=0.0,
        )
        + case((TAG_PREDICATES["quote_relaxed"], WEIGHTS["quote_relaxed"]), else_=0.0)
        + case(
            (TAG_PREDICATES["citation_corrected"], WEIGHTS["citation_corrected"]),
            else_=0.0,
        )
        + case(
            (TAG_PREDICATES["weak_evidence"], WEIGHTS["weak_evidence"] + graded),
            else_=0.0,
        )
    )


def _base_conditions(window_days: int):
    """INNER JOIN 诊断表本身就把 7/1 之前的老消息挡在外面 —— 它们没有诊断行,
    而坏引用的证据在入库时已被 verify_quoted_content 抹平,无法追溯。"""
    since = datetime.now(UTC) - timedelta(days=window_days)
    reviewed = select(AnswerReview.message_id)
    return [
        _M.role == "assistant",
        _M.created_at >= since,
        _M.id.not_in(reviewed),
    ]


def _diag_of(row_d: ChatAnswerDiagnostic) -> DiagnosticSignals:
    return DiagnosticSignals(
        citation_count=row_d.citation_count or 0,
        source_count=row_d.source_count or 0,
        quote_mutation_count=row_d.quote_mutation_count or 0,
        citation_mutation_count=row_d.citation_mutation_count or 0,
        max_source_score=row_d.max_source_score,
    )


async def count_unreviewed(db: AsyncSession, *, window_days: int = 30) -> int:
    """角标专用:只跑 COUNT,不打分、不拉 sources。导航每次都会读它。"""
    stmt = (
        select(func.count())
        .select_from(_M)
        .join(_D, _D.message_id == _M.id)
        .where(*_base_conditions(window_days), or_(*TAG_PREDICATES.values()))
    )
    return (await db.execute(stmt)).scalar_one()


async def build_bad_answer_queue(
    db: AsyncSession,
    *,
    window_days: int = 30,
    min_suspicion: float = 0.0,
    category: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """引用不可核对的回答队列,按可疑度降序。排序/分页/计数全部在 SQL 内完成。"""
    base = _base_conditions(window_days)
    score = _score_expr()

    requested = _requested_categories(category)
    tag_filter = or_(
        *[TAG_PREDICATES[t] for t in requested if t in TAG_PREDICATES]
    ) if requested else or_(*TAG_PREDICATES.values())

    conds = [*base, tag_filter, score >= min_suspicion]

    total = (
        await db.execute(
            select(func.count())
            .select_from(_M)
            .join(_D, _D.message_id == _M.id)
            .where(*conds)
        )
    ).scalar_one()

    rows = (
        await db.execute(
            select(_M, _D)
            .join(_D, _D.message_id == _M.id)
            .where(*conds)
            .order_by(score.desc(), _M.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    items: list[QueueItem] = []
    for m, d in rows:
        tags, s = classify_answer(m.content, m.feedback, _diag_of(d))
        items.append(
            QueueItem(
                message_id=m.id,
                session_id=m.session_id,
                answer=m.content,
                sources=_clean_sources(m.sources),
                reason_tags=tags,
                suspicion_score=s,
                feedback=m.feedback,
                created_at=m.created_at,
            )
        )
    await _attach_questions(db, items)

    # 标签分布:事后据此校准 WEAK_EVIDENCE_THRESHOLD(本次不动 0.37 这个数值)。
    dist_row = (
        await db.execute(
            select(
                *[
                    func.sum(case((pred, 1), else_=0)).label(tag)
                    for tag, pred in TAG_PREDICATES.items()
                ]
            )
            .select_from(_M)
            .join(_D, _D.message_id == _M.id)
            .where(*base, or_(*TAG_PREDICATES.values()))
        )
    ).one()
    tag_distribution = {
        tag: int(val or 0) for tag, val in zip(TAG_PREDICATES.keys(), dist_row)
    }

    # 来源分数分布仍取窗口内 *全部* 有诊断的回答(不只可疑的),用于校准阈值。
    samples = [
        float(v)
        for (v,) in (
            await db.execute(
                select(_D.max_source_score)
                .select_from(_M)
                .join(_D, _D.message_id == _M.id)
                .where(*base, _D.max_source_score.is_not(None))
            )
        ).all()
    ]

    return {
        "total_unreviewed": total,
        "score_distribution": _percentiles(samples),
        "tag_distribution": tag_distribution,
        "items": [asdict(it) for it in items],
    }
```

删除旧的 `_max_source_score` 辅助函数(第 42-55 行)——打分改从诊断行取 `max_source_score`,它已无人调用(全仓库仅 `answer_quality.py` 内部用过)。**同时删掉它的测试** `test_max_source_score_handles_bad_json`(`backend/tests/test_answer_quality.py:92-96`)与顶部 import,否则测试会 `ImportError`。

`_clean_sources`、`_percentiles`、`_attach_questions`、`QueueItem`、`_is_failed_answer` 保留不动。

> `_is_failed_answer` 不再需要在队列里逐条过滤:失败回答在 `chat.py:191` 就被拦住不入库了,且它们不会有诊断行。保留函数本身(仍被 chat 服务引用)。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && pytest tests/test_answer_quality.py -q`
Expected: PASS(全部)

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/answer_quality.py backend/tests/test_answer_quality.py
git commit -m "perf(admin): 差答案队列改为 join 诊断表 + SQL 下推排序分页计数"
```

---

### Task 3: `upsert_review` 适配新签名

**Files:**
- Modify: `backend/app/services/answer_quality.py:237-285`
- Test: `backend/tests/test_answer_quality.py`

**Interfaces:**
- Consumes: Task 1 的 `classify_answer(content, feedback, diag)`、Task 2 的 `count_unreviewed`。
- Produces: `upsert_review(...) -> int` 签名不变,但内部改为读诊断行、且返回值改用 `count_unreviewed`(不再重建整个队列)。

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.anyio
async def test_upsert_review_snapshots_new_tags_and_returns_cheap_count(session):
    mid = await _answer(
        session,
        diag=dict(citation_count=1, source_count=0, quote_mutation_count=0,
                  citation_mutation_count=0, max_source_score=None),
    )
    remaining = await upsert_review(
        session, message_id=mid, verdict="bad", failure_category="hallucination",
        note=None, reviewed_by=1,
    )
    assert remaining == 0  # 唯一一条已复核
    row = (
        await session.execute(select(AnswerReview).where(AnswerReview.message_id == mid))
    ).scalar_one()
    assert row.detection_reasons == ["fabricated_citation"]
    assert row.suspicion_score == 4.0


@pytest.mark.anyio
async def test_upsert_review_rejects_message_without_diagnostic(session):
    mid = await _answer(session, diag=None)
    with pytest.raises(ValueError):
        await upsert_review(
            session, message_id=mid, verdict="good", failure_category=None,
            note=None, reviewed_by=1,
        )
```

记得在测试文件顶部 import `upsert_review`。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && pytest tests/test_answer_quality.py -q -k upsert`
Expected: FAIL — `TypeError: classify_answer() takes 3 positional arguments but 4 were given`(旧实现仍按老签名调用)

- [ ] **Step 3: 实现**

把 `upsert_review` 里第 250-256 行与第 284 行改为:

```python
    row = (
        await db.execute(
            select(ChatMessage, ChatAnswerDiagnostic)
            .join(ChatAnswerDiagnostic, ChatAnswerDiagnostic.message_id == ChatMessage.id)
            .where(ChatMessage.id == message_id)
        )
    ).first()
    if row is None:
        raise ValueError("message not found, not an assistant message, or has no diagnostic")
    msg, diag_row = row
    if msg.role != "assistant":
        raise ValueError("message not found or not an assistant message")

    tags, score = classify_answer(msg.content, msg.feedback, _diag_of(diag_row))
```

并把函数末尾的

```python
    result = await build_bad_answer_queue(db, limit=0)
    return result["total_unreviewed"]
```

替换为:

```python
    return await count_unreviewed(db)
```

同时把 docstring 里的 "last 90 days" 改为 "the default window"。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && pytest tests/test_answer_quality.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/answer_quality.py backend/tests/test_answer_quality.py
git commit -m "refactor(admin): upsert_review 读诊断行,剩余数改用便宜 COUNT"
```

---

### Task 4: 端点 —— 窗口默认 30、吐标签分布、新增角标汇总

**Files:**
- Modify: `backend/app/schemas/admin.py:193-204`(加 `tag_distribution`;新增 `AdminPendingSummary`)
- Modify: `backend/app/api/admin.py:196-218`(window 默认 30)
- Modify: `backend/app/api/admin.py`(新增 `GET /admin/pending-summary`)
- Test: `backend/tests/test_admin.py`

**Interfaces:**
- Consumes: Task 2 的 `count_unreviewed`。
- Produces:
  ```python
  class AdminPendingSummary(BaseModel):
      answer_quality: int
      alignment_candidates: int
      suggestions: int
      feedbacks: int
      annotations: int
  # GET /api/admin/pending-summary -> AdminPendingSummary
  ```

- [ ] **Step 1: 写失败测试**

追加到 `backend/tests/test_admin.py`:

先打开 `backend/tests/test_admin.py:101-145`(`test_module_usage_requires_admin` / `test_module_usage_returns_data`)——**照抄它们的鉴权与 mock 写法**,不要新造 fixture。然后按同样的骨架追加:

```python
@pytest.mark.anyio
async def test_pending_summary_requires_admin(client):
    resp = await client.get("/api/admin/pending-summary")
    assert resp.status_code in (401, 403)


@pytest.mark.anyio
async def test_pending_summary_shape(client):
    """五个计数齐全 —— 角标是它的唯一消费者,少一个前端就会漏报待办。"""
    with patch(
        "app.api.admin.count_unreviewed", new=AsyncMock(return_value=7)
    ), patch(
        "app.api.admin.count_pending_candidates", new=AsyncMock(return_value=50)
    ), patch(
        "app.api.admin.count_pending_simple", new=AsyncMock(side_effect=[4, 3, 2])
    ):
        # 鉴权:与 test_module_usage_returns_data 完全一致地覆盖 require_role
        resp = await client.get("/api/admin/pending-summary")
        assert resp.status_code == 200
        assert resp.json() == {
            "answer_quality": 7,
            "alignment_candidates": 50,
            "suggestions": 4,
            "feedbacks": 3,
            "annotations": 2,
        }
```

> `count_pending_simple` 的 `side_effect=[4, 3, 2]` 依赖端点里 **suggestions → feedbacks → annotations** 的调用顺序;实现时保持这个顺序,否则断言会错位。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && pytest tests/test_admin.py -q -k pending_summary`
Expected: FAIL — 404(端点不存在)

- [ ] **Step 3: 实现**

`backend/app/schemas/admin.py` —— 在 `AnswerQueueResponse`(第 200 行)加一个字段,并新增汇总模型:

```python
class AnswerQueueResponse(BaseModel):
    total_unreviewed: int
    score_distribution: ScoreDistribution
    # 标签 -> 命中条数。用来事后校准 WEAK_EVIDENCE_THRESHOLD(现为 0.37,而生产
    # 实测分布已是 p10=0.31 —— 阈值偏高在误报,但本次不拍脑袋改数值)。
    tag_distribution: dict[str, int] = Field(default_factory=dict)
    items: list[AnswerQueueItem]


class AdminPendingSummary(BaseModel):
    """侧边栏角标的唯一数据源。全部是 COUNT,导航每次都会读。"""

    answer_quality: int
    alignment_candidates: int
    suggestions: int
    feedbacks: int
    annotations: int
```

`backend/app/services/admin_service.py` —— 追加两个便宜的计数辅助:

```python
from app.models.alignment_candidate import AlignmentCandidate
from app.models.feedback import Feedback


async def count_pending_candidates(db: AsyncSession) -> int:
    return (await db.execute(
        select(func.count()).select_from(AlignmentCandidate)
        .where(AlignmentCandidate.status == "pending")
    )).scalar_one()


async def count_pending_simple(db: AsyncSession, model) -> int:
    """SourceSuggestion / Feedback / Annotation 三者的 pending 计数同构。"""
    return (await db.execute(
        select(func.count()).select_from(model).where(model.status == "pending")
    )).scalar_one()
```

`backend/app/api/admin.py` —— 在 `answer_quality_queue`(第 196-218 行)把 `window` 默认值改为 `30`:

```python
@router.get("/answer-quality/queue", response_model=AnswerQueueResponse)
async def answer_quality_queue(
    window: int = Query(30, ge=1, le=365),
```

并把 docstring 改为:

```python
    """引用不可核对的回答队列(凭空引用 / 转述当原文引 / 引用被纠正 / 弱证据 /
    点踩 / 异常短)。只覆盖有诊断行的消息 —— 2026-07-01 之前的回答,坏引用的证据
    在入库时已被 verify_quoted_content 抹平,无法追溯。``tag_distribution`` 与
    ``score_distribution`` 用于校准阈值。"""
```

新增端点(放在 `answer_quality_review_stats` 之后):

```python
@router.get("/pending-summary", response_model=AdminPendingSummary)
async def pending_summary(
    _user=Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """侧边栏角标。全部走 COUNT —— 不能在这里跑打分,导航每次都会读它。"""
    return AdminPendingSummary(
        answer_quality=await count_unreviewed(db),
        alignment_candidates=await count_pending_candidates(db),
        suggestions=await count_pending_simple(db, SourceSuggestion),
        feedbacks=await count_pending_simple(db, Feedback),
        annotations=await count_pending_simple(db, Annotation),
    )
```

并补齐 import:

```python
from app.models.annotation import Annotation
from app.models.feedback import Feedback
from app.models.source_suggestion import SourceSuggestion
from app.schemas.admin import AdminPendingSummary
from app.services.admin_service import count_pending_candidates, count_pending_simple
from app.services.answer_quality import count_unreviewed
```

> 若 `Annotation` / `SourceSuggestion` 的 import 路径与上面不符,以 `backend/app/services/admin_service.py` 顶部已有的 import 为准(那里已经在用这两个模型算 `pending_suggestions` / `pending_annotations`)。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && pytest tests/test_admin.py tests/test_answer_quality.py -q`
Expected: PASS

- [ ] **Step 5: 提交并开 PR 1**

```bash
git add backend/
git commit -m "feat(admin): 角标汇总端点 + 队列吐标签分布,窗口默认收窄到 30 天"
git push -u origin feat/admin-console-optimization
gh pr create --title "feat(admin): 差答案队列判据改为「引用可核对性」+ SQL 下推" --body "$(cat <<'EOF'
## 为什么

差答案队列 715 条积压、零复核。首页全是 `no_citation`,里面混着 `what can you do today?`、`请转换成 markdown 模式` 这类**根本不需要引经**的问题 —— 判据把"没有来源"当成"差答案",信号被噪音淹没,所以没人用。

## 改了什么

判据从「有没有引经」换成「**引用是否可核对**」:join `chat_answer_diagnostics`,收录**凭空引用**(引了经却零来源)、**转述当原文引**、**引用被系统纠正**、弱证据、点踩、异常短。删除 `no_citation`。

顺带把全表扫修了:判据全是诊断表上的列比较,排序/分页/计数下推到 SQL(旧实现把窗口内每条消息连同完整 `sources` JSON 拉进 Python 内存分页,实测 1.8s / 80KB)。新增便宜的 `GET /admin/pending-summary` 供侧边栏角标使用。

## 已知代价

2026-07-01(诊断表落地)之前的消息不进队列。`verify_quoted_content` 的契约是"fojin 从不端出假的逐字引用",对不上的引号在**入库前**就被剥掉了 —— 坏引用的证据已被销毁,任何"重算"都只会得出假的"一切正常"。窗口默认从 90 天收窄到 30 天。

阈值 `WEAK_EVIDENCE_THRESHOLD` 本次**不动**(仍为 0.37,而生产实测 p10 已降到 0.31 —— 偏高在误报)。先让队列把 `tag_distribution` 吐出来,看真实分布再调。

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

# PR 2 — 前端:菜单重排 + 角标 + 错误态

### Task 5: client.ts —— 角标汇总 API 与类型

**Files:**
- Modify: `frontend/src/api/client.ts:1364-1400`

**Interfaces:**
- Consumes: Task 4 的 `GET /api/admin/pending-summary`。
- Produces:
  ```ts
  export interface AdminPendingSummary {
    answer_quality: number;
    alignment_candidates: number;
    suggestions: number;
    feedbacks: number;
    annotations: number;
  }
  export async function getAdminPendingSummary(): Promise<AdminPendingSummary>
  ```
  并给已有的 `AnswerQueueResponse`(第 1364 行)加上 `tag_distribution: Record<string, number>`。

- [ ] **Step 1: 实现(纯类型 + 一个 GET,无独立单测;由 Task 9 的组件测试覆盖)**

在 `frontend/src/api/client.ts` 中,`AnswerQueueResponse` 接口加一行:

```ts
export interface AnswerQueueResponse {
  total_unreviewed: number;
  score_distribution: ScoreDistribution;
  tag_distribution: Record<string, number>;
  items: AnswerQueueItem[];
}
```

在 `getAnswerReviewStats`(第 1402 行)之后追加:

```ts
export interface AdminPendingSummary {
  answer_quality: number;
  alignment_candidates: number;
  suggestions: number;
  feedbacks: number;
  annotations: number;
}

/** 侧边栏角标的唯一数据源:一次请求拿全部待办计数(后端全部走 COUNT)。 */
export async function getAdminPendingSummary(): Promise<AdminPendingSummary> {
  const { data } = await api.get<AdminPendingSummary>("/admin/pending-summary");
  return data;
}
```

- [ ] **Step 2: 类型检查**

Run: `cd frontend && npx tsc --noEmit`
Expected: 无新增错误

- [ ] **Step 3: 提交**

```bash
git add frontend/src/api/client.ts
git commit -m "feat(admin): 前端接入 pending-summary 与 tag_distribution"
```

---

### Task 6: 差答案队列页的错误态(必修)

**Files:**
- Modify: `frontend/src/pages/AdminAnswerQualityPage.tsx:56-90`、`:186-200`
- Test: `frontend/src/pages/AdminAnswerQualityPage.test.tsx`

**为什么是必修:** 现在两个请求包在同一个 `Promise.all` 里,任一失败就走 `.catch()`,只弹一个 toast,而 `total` 保持初始值 `0`、表格渲染成「队列已清空」。**请求失败与队列真空在 UI 上完全同形** —— 这正是 715 条积压长期被当成"空队列"的直接原因。

**Interfaces:**
- Consumes: `getAnswerQualityQueue` / `getAnswerReviewStats`(已存在)。
- Produces: 无对外接口;新增组件内部状态 `loadError: boolean`。

- [ ] **Step 1: 写失败测试**

追加到 `frontend/src/pages/AdminAnswerQualityPage.test.tsx`:

```tsx
it("请求失败时显示错误态,而不是渲染成「队列已清空」", async () => {
  vi.mocked(getAnswerQualityQueue).mockRejectedValueOnce(new Error("boom"));
  vi.mocked(getAnswerReviewStats).mockResolvedValueOnce({
    reviewed_total: 0, good: 0, bad: 0, by_category: {}, last_reviewed_at: null,
  });

  render(<AdminAnswerQualityPage />);

  expect(await screen.findByRole("alert")).toBeInTheDocument();
  expect(screen.queryByText(/队列已清空/)).not.toBeInTheDocument();
  expect(screen.queryByText(/未复核\s*0\s*条/)).not.toBeInTheDocument();
});
```

> mock 与 render 的写法照抄该文件已有用例。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd frontend && npx vitest run src/pages/AdminAnswerQualityPage.test.tsx`
Expected: FAIL — 找不到 `role="alert"`,且「队列已清空」仍然渲染

- [ ] **Step 3: 实现**

`AdminAnswerQualityPage.tsx` 第 56-60 行附近新增状态:

```tsx
  const [loadError, setLoadError] = useState(false);
```

把 `load`(第 68-90 行)改为:

```tsx
  const load = useCallback(() => {
    return Promise.all([
      getAnswerQualityQueue({
        window: windowDays,
        min_suspicion: minSuspicion,
        category: reasonFilters.length ? reasonFilters.join(",") : undefined,
        limit: 50,
      }),
      getAnswerReviewStats(),
    ])
      .then(([res, stats]) => {
        setItems(res.items);
        setTotal(res.total_unreviewed);
        setDist(res.score_distribution);
        setReviewStats(stats);
        setLoadError(false);
      })
      .catch(() => {
        // 失败必须显性化:此前只弹 toast、把 total 留在初始 0,于是 500 和
        // 「队列真的空」长得一模一样 —— 715 条积压就是这样被当成空队列的。
        setLoadError(true);
        setItems([]);
        message.error(t("admin_aq.load_error"));
      })
      .finally(() => {
        setLoading(false);
      });
  }, [minSuspicion, reasonFilters, t, windowDays]);
```

在第 186-190 行(渲染 `未复核 {count} 条` 的那一行)之前插入错误横幅,并让计数在出错时不显示:

```tsx
      {loadError && (
        <Alert
          role="alert"
          type="error"
          showIcon
          style={{ marginBottom: 12 }}
          message={t("admin_aq.load_error")}
          action={<Button size="small" onClick={() => { setLoading(true); load(); }}>{t("common.retry")}</Button>}
        />
      )}
      {!loadError && (
        <span>{t("admin_aq.unreviewed_total", { count: total })}</span>
      )}
```

并把表格的 `locale={{ emptyText: ... }}`(第 260 行)改为:

```tsx
        locale={{ emptyText: loadError ? t("admin_aq.load_error") : t("admin_aq.queue_empty") }}
```

从 antd 补 import:`import { Alert, Button } from "antd";`(若已 import 则合并)。

i18n:在 `frontend/public/locales/zh/translation.json` 与 `en/translation.json` 中确保存在 `common.retry`(中文 `"重试"`,英文 `"Retry"`);`admin_aq.load_error` 已存在。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd frontend && npx vitest run src/pages/AdminAnswerQualityPage.test.tsx`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add frontend/src/pages/AdminAnswerQualityPage.tsx frontend/src/pages/AdminAnswerQualityPage.test.tsx frontend/public/locales
git commit -m "fix(admin): 差答案队列请求失败显示错误态,不再伪装成「队列已清空」"
```

---

### Task 7: 跨藏对齐页内 tab 合并(给隐藏页补门牌)

**Files:**
- Modify: `frontend/src/pages/AdminAlignmentPage.tsx:100-135`
- Modify: `frontend/src/App.tsx:96-105`

**为什么:** `/admin/alignment/review` 有 **50 条待处理**,是后台里唯一会**直接改写生产语料**(接受即写入 `alignment_pairs`)的写队列,却不在菜单里,只能从覆盖率页右上角一个链接点进去。

**Interfaces:**
- Consumes: 已有的 `AdminAlignmentPage`(覆盖率看板)与 `AlignmentReviewPage`(候选复核)两个组件。
- Produces: `/admin/alignment` 渲染 Tabs;`/admin/alignment/review` 保留为深链(直接落到「候选复核」tab)。

- [ ] **Step 1: 实现**

在 `AdminAlignmentPage.tsx` 顶层用 antd `Tabs` 包住原有内容,并把 `AlignmentReviewPage` 作为第二个 tab:

```tsx
import { Tabs } from "antd";
import { useLocation, useNavigate } from "react-router-dom";
import AlignmentReviewPage from "./AlignmentReviewPage";

// ...组件内:
  const location = useLocation();
  const navigate = useNavigate();
  const activeKey = location.pathname.endsWith("/review") ? "review" : "coverage";

  return (
    <Tabs
      activeKey={activeKey}
      onChange={(k) =>
        navigate(k === "review" ? "/admin/alignment/review" : "/admin/alignment")
      }
      items={[
        { key: "coverage", label: t("nav.admin_alignment"), children: <CoveragePanel /> },
        { key: "review", label: t("nav.admin_alignment_review"), children: <AlignmentReviewPage /> },
      ]}
    />
  );
```

把原本 `AdminAlignmentPage` 里渲染覆盖率表格的那段 JSX 抽成同文件内的 `CoveragePanel` 组件(纯搬移,不改逻辑),并**删除**第 127 行那个 `<Link to="/admin/alignment/review">复核候选对齐</Link>` —— 它的功能已被 tab 取代。

`App.tsx` 第 104-105 行改为让两条路由都渲染 `AdminAlignmentPage`(由它按 pathname 选中 tab):

```tsx
              <Route path="/admin/alignment" element={<AdminAlignmentPage />} />
              <Route path="/admin/alignment/review" element={<AdminAlignmentPage />} />
```

i18n:在 `zh/translation.json` 加 `"nav.admin_alignment_review": "候选复核"`,`en/translation.json` 加 `"nav.admin_alignment_review": "Candidate review"`。

- [ ] **Step 2: 手工验证**

Run: `cd frontend && npm run dev`
打开 `/admin/alignment` → 应看到两个 tab,默认「覆盖率」;点「候选复核」→ URL 变为 `/admin/alignment/review`,列出 50 条候选;直接访问 `/admin/alignment/review` → 直接落在「候选复核」tab。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/pages/AdminAlignmentPage.tsx frontend/src/App.tsx frontend/public/locales
git commit -m "feat(admin): 跨藏对齐页合并覆盖率与候选复核两个 tab"
```

---

### Task 8: 「待办」页(源建议 / 用户反馈 / 标注审核 三合一)

**Files:**
- Create: `frontend/src/pages/AdminInboxPage.tsx`
- Modify: `frontend/src/App.tsx:96-105`

**为什么:** 这三项当前待办**全是 0**(源建议 4 条全已采纳、反馈 4 条全已解决、标注 3 条历史)。它们是被动响应型队列,没人提交就不该占常驻菜单位。

**Interfaces:**
- Consumes: 已有的 `AdminSuggestionsPage` / `AdminFeedbacksPage` / `AdminAnnotationsPage` 组件(原样复用,不改)。
- Produces: `/admin/inbox` 渲染三 tab;`/admin/suggestions`、`/admin/feedbacks`、`/admin/annotations` 三条旧路由保留为深链。

- [ ] **Step 1: 实现**

新建 `frontend/src/pages/AdminInboxPage.tsx`:

```tsx
import { Tabs } from "antd";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";

import AdminAnnotationsPage from "./AdminAnnotationsPage";
import AdminFeedbacksPage from "./AdminFeedbacksPage";
import AdminSuggestionsPage from "./AdminSuggestionsPage";

/** 待办:三个被动响应型队列(有人提交才需要处理)合成一个入口。
 *  侧边栏角标为 0 时,菜单里整项不显示 —— 见 Layout.tsx。 */
const TAB_PATHS: Record<string, string> = {
  suggestions: "/admin/suggestions",
  feedbacks: "/admin/feedbacks",
  annotations: "/admin/annotations",
};

export default function AdminInboxPage() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();

  const activeKey =
    Object.keys(TAB_PATHS).find((k) => location.pathname === TAB_PATHS[k]) ??
    "suggestions";

  return (
    <Tabs
      activeKey={activeKey}
      onChange={(k) => navigate(TAB_PATHS[k])}
      items={[
        { key: "suggestions", label: t("nav.admin_suggestions"), children: <AdminSuggestionsPage /> },
        { key: "feedbacks", label: t("nav.admin_feedbacks"), children: <AdminFeedbacksPage /> },
        { key: "annotations", label: t("nav.admin_annotations"), children: <AdminAnnotationsPage /> },
      ]}
    />
  );
}
```

`App.tsx` 里把这三条路由改为渲染 `AdminInboxPage`,并新增 `/admin/inbox`:

```tsx
              <Route path="/admin/inbox" element={<AdminInboxPage />} />
              <Route path="/admin/suggestions" element={<AdminInboxPage />} />
              <Route path="/admin/annotations" element={<AdminInboxPage />} />
              <Route path="/admin/feedbacks" element={<AdminInboxPage />} />
```

并在 `App.tsx` 顶部按既有 lazy-import 风格加上 `AdminInboxPage` 的 import。

i18n:`zh/translation.json` 加 `"nav.admin_inbox": "待办"`,`en/translation.json` 加 `"nav.admin_inbox": "Inbox"`。

- [ ] **Step 2: 跑既有 CRUD 测试确认没弄坏**

Run: `cd frontend && npx vitest run src/pages/AdminCrudPages.test.tsx`
Expected: PASS(三个子页面组件未改动)

- [ ] **Step 3: 提交**

```bash
git add frontend/src/pages/AdminInboxPage.tsx frontend/src/App.tsx frontend/public/locales
git commit -m "feat(admin): 新增「待办」页,三个被动队列合并为一个入口"
```

---

### Task 9: 菜单重排 + 逐项角标(桌面端 + 移动端两处)

**Files:**
- Modify: `frontend/src/components/Layout.tsx:61-113`(数据 + 菜单数组)
- Modify: `frontend/src/components/Layout.tsx:184-193`(桌面端 Dropdown 渲染)
- Modify: `frontend/src/components/Layout.tsx:348-365`(移动端渲染 —— **别漏了这处**)
- Modify: `frontend/src/pages/AdminUsersPage.tsx`(把审计日志入口挂过去)

**Interfaces:**
- Consumes: Task 5 的 `getAdminPendingSummary()`。
- Produces: 常驻 4 项 + 角标;`待办` 在计数为 0 时整项不渲染。

- [ ] **Step 1: 实现 —— 数据源换成一次汇总请求**

把 `Layout.tsx` 第 61-69 行替换为:

```tsx
  const [pending, setPending] = useState<AdminPendingSummary | null>(null);
  const isAdmin = user?.role === "admin";

  useEffect(() => {
    if (!isAdmin) return;
    getAdminPendingSummary().then(setPending).catch(() => {});
  }, [isAdmin, location.pathname]);

  const inboxCount =
    (pending?.suggestions ?? 0) + (pending?.feedbacks ?? 0) + (pending?.annotations ?? 0);
  const adminBadgeTotal =
    (pending?.answer_quality ?? 0) + (pending?.alignment_candidates ?? 0) + inboxCount;
```

import 改为 `import { getAdminPendingSummary, type AdminPendingSummary } from "../api/client";`(替换掉 `getPendingSuggestionCount` / `getPendingFeedbackCount` 两个 import)。

- [ ] **Step 2: 实现 —— 菜单数组**

把类型声明(第 71-76 行)里的 `children` 改成带计数:

```tsx
  const navItems: Array<{
    icon: ReactNode;
    label: string;
    path: string;
    children?: Array<{ label: string; path: string; count?: number }>;
  }> = [
```

把 admin 那一块(第 94-112 行)替换为:

```tsx
    ...(isAdmin
      ? [
          {
            icon: <Badge count={adminBadgeTotal} size="small" offset={[4, -2]}><DashboardOutlined /></Badge>,
            label: t("nav.admin"),
            path: "/admin",
            // 常驻 4 项。判据是「需不需要你主动定期查看」:
            //   概览/用户管理 = 日常;差答案队列 + 跨藏对齐 = 有积压要处理。
            // 源建议/反馈/标注是被动响应型队列(没人提交就没活儿)→ 收进「待办」,
            // 计数为 0 时整项不渲染。审计日志移出菜单(挂在用户管理页)。
            children: [
              { label: t("nav.admin_overview"), path: "/admin" },
              { label: t("nav.admin_users"), path: "/admin/users" },
              {
                label: t("nav.admin_answer_quality"),
                path: "/admin/answer-quality",
                count: pending?.answer_quality ?? 0,
              },
              {
                label: t("nav.admin_alignment"),
                path: "/admin/alignment",
                count: pending?.alignment_candidates ?? 0,
              },
              ...(inboxCount > 0
                ? [{ label: t("nav.admin_inbox"), path: "/admin/inbox", count: inboxCount }]
                : []),
            ],
          },
        ]
      : []),
```

- [ ] **Step 3: 实现 —— 两处渲染都要显示角标**

桌面端(第 188-192 行)改为:

```tsx
                    items: item.children.map((child) => ({
                      key: child.path,
                      label: child.count ? (
                        <Badge
                          count={child.count}
                          size="small"
                          offset={[10, 0]}
                          style={{ marginLeft: 8 }}
                        >
                          <span>{child.label}</span>
                        </Badge>
                      ) : (
                        child.label
                      ),
                      onClick: () => navigate(child.path),
                    })),
```

移动端(第 359 行那个 `item.children.map((child) => (` 循环)在 child 的 label 后同样挂上 `child.count ? <Badge ... /> : null`,与桌面端保持一致的写法。

- [ ] **Step 4: 实现 —— 审计日志挂到用户管理页**

在 `frontend/src/pages/AdminUsersPage.tsx` 的标题行右侧(与搜索框同一行)加一个链接:

```tsx
<Link to="/admin/audit-log" style={{ fontSize: 13 }}>{t("nav.admin_audit_log")}</Link>
```

(`/admin/audit-log` 路由保持不变,不删。审计日志当前是空表,且漏审了最危险的写操作——补全审计覆盖是另一个 PR。)

- [ ] **Step 5: 手工验证**

Run: `cd frontend && npm run dev`
- 管理菜单只有 **4 项**(数据概览 / 用户管理 / 差答案队列 / 跨藏对齐),因为三个待办队列当前都是 0
- 差答案队列与跨藏对齐后面各有角标(数字应与后端 `/api/admin/pending-summary` 一致)
- 窄屏(移动端抽屉)里同样能看到 4 项与角标
- 用户管理页右上角能点到审计日志

- [ ] **Step 6: 提交并开 PR 2**

```bash
git add frontend/
git commit -m "feat(admin): 后台菜单常驻收敛到 4 项,待办合并 + 逐项角标"
git push
gh pr create --title "feat(admin): 后台菜单重排 + 队列错误态" --body "$(cat <<'EOF'
## 为什么

后台 8 项常驻菜单里,只有 2 个地方真有活儿 —— 而这两个都没被用起来,其中一个**连菜单入口都没有**:

| 页面 | 待处理 |
|---|---|
| 差答案队列 | **715** |
| 候选对齐复核(**不在菜单里**) | **50** |
| 源建议 / 用户反馈 / 标注审核 | 0 / 0 / 0 |
| 审计日志 | 0(空表) |

## 改了什么

- 常驻收敛到 **4 项**:数据概览、用户管理、差答案队列`[角标]`、跨藏对齐`[角标]`
- **跨藏对齐**页内合并「覆盖率」+「候选复核」两个 tab —— 那个会**直接改写生产语料**的写队列从此有门牌
- 源建议 / 反馈 / 标注 → 合并为「待办」页,**角标为 0 时整项不渲染**(当前三者皆 0,故平时只见 4 项)
- 审计日志移出菜单,入口挂到用户管理页(路由保留)
- 角标改走一次 `GET /admin/pending-summary`(全 COUNT),不再触发队列打分

## 顺带修掉一个会骗人的 bug

差答案队列页此前把两个请求包在 `Promise.all` 里,任一失败就只弹 toast、把计数留在初始 `0`、表格渲染成「队列已清空」—— **请求失败与队列真空完全同形**。这正是 715 条积压长期被当成"空队列"的直接原因。现在失败会显示错误态与重试按钮。

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## 完成后的验收

- [ ] `cd backend && pytest tests/test_answer_quality.py tests/test_admin.py -q` 全绿
- [ ] `cd frontend && npx vitest run src/pages/AdminAnswerQualityPage.test.tsx src/pages/AdminCrudPages.test.tsx` 全绿
- [ ] `cd frontend && npx tsc --noEmit` 无新增错误
- [ ] 生产验证(合并部署后):`/admin` 菜单为 4 项;`/admin/answer-quality` 的 `tag_distribution` 有真实分布;`/admin/alignment` 能看到 50 条候选

## 后续(不在本计划内)

1. **按 `tag_distribution` 校准 `WEAK_EVIDENCE_THRESHOLD`**(现 0.37,生产 p10 已是 0.31)。
2. **补全审计覆盖**:`record_audit()` 只在 3 处被调用;**对齐候选 accept 会直接写入 `alignment_pairs` 却零审计**(`alignment_review.py:77-90`)。
3. **`reviewer` 死角色**:后端接受,前端 `/admin/*` 只认 `admin`,该角色无任何 UI 入口。
4. **飞轮上游**:`mine_candidates` / `mine_from_anchors` 没有 CLI / HTTP / cron,只能手工跑 heredoc。50 条候选耗尽后需人工再挖。
