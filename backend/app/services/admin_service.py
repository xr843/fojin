import logging
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Date, and_, case, cast, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_get as _cache_get
from app.core.cache import cache_set
from app.models.alignment_candidate import AlignmentCandidate
from app.models.annotation import Annotation
from app.models.audit import AdminAuditLog
from app.models.chat import ChatMessage, ChatSession
from app.models.source import SourceSuggestion
from app.models.user import ReadingHistory, User
from app.schemas.admin import (
    AdminAnnotationItem,
    AdminAuditLogItem,
    AdminOverview,
    DailyCount,
)

logger = logging.getLogger(__name__)

OVERVIEW_CACHE_KEY = "admin:stats:overview"
TRENDS_CACHE_KEY_PREFIX = "admin:stats:trends:"  # full key appends the days window
OVERVIEW_CACHE_TTL = 300  # 5 minutes

# Server, ops team, and end users all live in CST. created_at columns are stored
# in UTC, so we explicitly anchor "today" / day-bucket boundaries to CST and
# convert when crossing the SQL ↔ Python boundary, instead of letting Postgres'
# session timezone or Python's naive date.today() pick the boundary implicitly.
LOCAL_TZ = ZoneInfo("Asia/Shanghai")


def _local_today() -> date:
    return datetime.now(LOCAL_TZ).date()


def _local_midnight_utc(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time(), tzinfo=LOCAL_TZ).astimezone(UTC)


async def get_overview(db: AsyncSession, redis=None) -> AdminOverview:
    cached = await _cache_get(redis, OVERVIEW_CACHE_KEY)
    if cached is not None:
        return AdminOverview(**cached)

    today = _local_today()
    today_start = _local_midnight_utc(today)
    yesterday_start = _local_midnight_utc(today - timedelta(days=1))

    total_users, new_users_today, new_users_yesterday = await _counts_with_buckets(
        db, User, User.created_at, today_start, yesterday_start
    )
    total_sessions, new_sessions_today, new_sessions_yesterday = await _counts_with_buckets(
        db, ChatSession, ChatSession.created_at, today_start, yesterday_start
    )
    total_messages, new_messages_today, new_messages_yesterday = await _counts_with_buckets(
        db, ChatMessage, ChatMessage.created_at, today_start, yesterday_start
    )

    pending_suggestions = (await db.execute(
        select(func.count()).select_from(SourceSuggestion).where(SourceSuggestion.status == "pending")
    )).scalar_one()

    pending_annotations = (await db.execute(
        select(func.count()).select_from(Annotation).where(Annotation.status == "pending")
    )).scalar_one()

    overview = AdminOverview(
        total_users=total_users,
        new_users_today=new_users_today,
        new_users_yesterday=new_users_yesterday,
        total_sessions=total_sessions,
        new_sessions_today=new_sessions_today,
        new_sessions_yesterday=new_sessions_yesterday,
        total_messages=total_messages,
        new_messages_today=new_messages_today,
        new_messages_yesterday=new_messages_yesterday,
        pending_suggestions=pending_suggestions,
        pending_annotations=pending_annotations,
        last_updated=datetime.now(UTC),
    )

    await _cache_set(redis, OVERVIEW_CACHE_KEY, overview.model_dump(mode="json"))
    return overview


async def _counts_with_buckets(
    db: AsyncSession,
    model,
    created_field,
    today_start: datetime,
    yesterday_start: datetime,
):
    """Single-pass COUNT for total / today / yesterday windows.

    Yesterday = [yesterday_start, today_start) so the windows do not overlap.
    """
    result = await db.execute(
        select(
            func.count(),
            func.count(case((created_field >= today_start, 1))),
            func.count(
                case((and_(created_field >= yesterday_start, created_field < today_start), 1))
            ),
        ).select_from(model)
    )
    row = result.one()
    return row[0], row[1], row[2]


async def _cache_set(redis, key: str, value: dict, ttl: int = OVERVIEW_CACHE_TTL) -> None:
    """Cache a value with this service's default TTL (delegates to core.cache)."""
    await cache_set(redis, key, value, ttl)


async def get_trends(db: AsyncSession, days: int = 30, redis=None) -> dict:
    cache_key = f"{TRENDS_CACHE_KEY_PREFIX}{days}"
    cached = await _cache_get(redis, cache_key)
    if cached is not None:
        return cached

    today = _local_today()
    since = today - timedelta(days=days - 1)
    since_dt = _local_midnight_utc(since)
    date_grid = [since + timedelta(days=i) for i in range(days)]

    registrations = await _daily_counts(db, User, User.created_at, since_dt, date_grid)
    messages = await _daily_counts(db, ChatMessage, ChatMessage.created_at, since_dt, date_grid)
    active_users = await _daily_active_users(db, since_dt, date_grid)

    # Stored as plain dicts so the Redis JSON round-trip is lossless;
    # AdminTrends(**result) coerces them back into DailyCount either way.
    result = {
        "registrations": [d.model_dump() for d in registrations],
        "messages": [d.model_dump() for d in messages],
        "active_users": [d.model_dump() for d in active_users],
    }
    await _cache_set(redis, cache_key, result)
    return result


def _fill_missing_days(rows: dict[date, int], date_grid: list[date]) -> list[DailyCount]:
    return [DailyCount(date=d.isoformat(), count=rows.get(d, 0)) for d in date_grid]


def _local_day(created_field):
    """Cast a UTC timestamptz column to its CST calendar date.

    `timezone('Asia/Shanghai', ts)` shifts a timestamptz into CST as a naive
    timestamp; casting that to Date gives the CST calendar day. Without this,
    Postgres falls back to the session timezone, which is environment-dependent
    and can disagree with the Python-side day boundary.
    """
    return cast(func.timezone("Asia/Shanghai", created_field), Date)


async def _daily_counts(
    db: AsyncSession, model, created_field, since: datetime, date_grid: list[date]
) -> list[DailyCount]:
    day_col = _local_day(created_field)
    result = await db.execute(
        select(day_col, func.count())
        .select_from(model)
        .where(created_field >= since)
        .group_by(day_col)
        .order_by(day_col)
    )
    rows = {row[0]: row[1] for row in result.all()}
    return _fill_missing_days(rows, date_grid)


async def _daily_active_users(
    db: AsyncSession, since: datetime, date_grid: list[date]
) -> list[DailyCount]:
    """Active users = distinct users who sent a chat message OR read a text each day.

    Chat activity keys off ``ChatMessage.created_at`` (joined to ChatSession for
    the owner), NOT ``ChatSession.created_at``. A user replying inside a session
    opened on an earlier day is active on the day they send the message — keying
    off session creation would miss every follow-up turn in an existing session.
    Only ``role='user'`` messages count, since an assistant reply is not the
    user doing something.
    """
    chat_day = _local_day(ChatMessage.created_at)
    read_day = _local_day(ReadingHistory.last_read_at)

    chat_q = (
        select(chat_day.label("day"), ChatSession.user_id.label("uid"))
        .select_from(ChatMessage)
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .where(
            ChatMessage.created_at >= since,
            ChatMessage.role == "user",
            ChatSession.user_id.is_not(None),
        )
    )
    read_q = (
        select(read_day.label("day"), ReadingHistory.user_id.label("uid"))
        .where(ReadingHistory.last_read_at >= since)
    )
    union_q = chat_q.union_all(read_q).subquery()

    result = await db.execute(
        select(union_q.c.day, func.count(distinct(union_q.c.uid)))
        .group_by(union_q.c.day)
        .order_by(union_q.c.day)
    )
    rows = {row[0]: row[1] for row in result.all()}
    return _fill_missing_days(rows, date_grid)


async def daily_active_user_detail(db: AsyncSession, target_day: date) -> dict:
    """Who was active on a given local day, and what they did.

    Mirrors _daily_active_users (chat OR read counts a user as active) but
    returns the per-user breakdown instead of just a count. Only logged-in
    users (chat sessions / reading history carry a user_id); anonymous chat
    has no identity to show.

    Day bounds use a half-open UTC range from _local_midnight_utc (index-
    friendly range scan on created_at) rather than _daily_active_users'
    cast(timezone('Asia/Shanghai', ts), Date) bucketing. The two partition
    every day identically — and the detail total reconciles with the trend
    point — ONLY because LOCAL_TZ is Asia/Shanghai (UTC+8, no DST), so each
    local day is one contiguous UTC interval. If LOCAL_TZ ever moves to a DST
    zone, switch this to _local_day to stay consistent across the transition.
    """
    start = _local_midnight_utc(target_day)
    end = _local_midnight_utc(target_day + timedelta(days=1))

    chat_rows = (await db.execute(
        select(ChatSession.user_id, func.count().label("n"))
        .select_from(ChatMessage)
        .join(ChatSession, ChatMessage.session_id == ChatSession.id)
        .where(
            ChatMessage.created_at >= start,
            ChatMessage.created_at < end,
            ChatMessage.role == "user",
            ChatSession.user_id.is_not(None),
        )
        .group_by(ChatSession.user_id)
    )).all()
    read_rows = (await db.execute(
        select(ReadingHistory.user_id, func.count().label("n"))
        .where(ReadingHistory.last_read_at >= start, ReadingHistory.last_read_at < end)
        .group_by(ReadingHistory.user_id)
    )).all()

    chat_by_uid = {uid: n for uid, n in chat_rows}
    read_by_uid = {uid: n for uid, n in read_rows}
    uids = set(chat_by_uid) | set(read_by_uid)
    if not uids:
        return {"date": target_day.isoformat(), "total": 0, "users": []}

    users = (await db.execute(select(User).where(User.id.in_(uids)))).scalars().all()
    detail = [
        {
            "user_id": u.id,
            "username": u.username,
            "display_name": u.display_name,
            "email": u.email,
            "role": u.role,
            "chat_messages": chat_by_uid.get(u.id, 0),
            "texts_read": read_by_uid.get(u.id, 0),
            "last_active_at": u.last_active_at,
            "api_provider": u.api_provider,
        }
        for u in users
    ]
    # Busiest first: chat is the heavier signal, then reading.
    detail.sort(key=lambda d: (d["chat_messages"], d["texts_read"]), reverse=True)
    return {"date": target_day.isoformat(), "total": len(detail), "users": detail}


async def list_users(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    q: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> tuple[int, list]:
    query = select(User)
    count_query = select(func.count()).select_from(User)

    if q:
        pattern = f"%{q}%"
        condition = User.username.ilike(pattern) | User.email.ilike(pattern)
        query = query.where(condition)
        count_query = count_query.where(condition)

    total = (await db.execute(count_query)).scalar_one()

    sort_col = getattr(User, sort_by, User.created_at)
    if sort_order == "asc":
        query = query.order_by(sort_col.asc().nullslast())
    else:
        query = query.order_by(sort_col.desc().nullsfirst())

    query = query.offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    return total, list(result.scalars().all())


async def list_annotations_for_review(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    status: str | None = None,
) -> tuple[int, list[AdminAnnotationItem]]:
    base = select(Annotation, User.username).join(User, Annotation.user_id == User.id)
    count_base = select(func.count()).select_from(Annotation)

    if status:
        base = base.where(Annotation.status == status)
        count_base = count_base.where(Annotation.status == status)

    total = (await db.execute(count_base)).scalar_one()

    query = base.order_by(Annotation.created_at.desc()).offset((page - 1) * size).limit(size)
    result = await db.execute(query)

    items = []
    for ann, username in result.all():
        items.append(AdminAnnotationItem(
            id=ann.id,
            text_id=ann.text_id,
            juan_num=ann.juan_num,
            annotation_type=ann.annotation_type,
            content=ann.content[:200],
            user_id=ann.user_id,
            username=username,
            status=ann.status,
            created_at=ann.created_at,
        ))
    return total, items


def record_audit(
    db: AsyncSession,
    actor_id: int | None,
    action: str,
    target_type: str,
    target_id: int | None = None,
    detail: dict | None = None,
) -> None:
    """Stage an audit-log row in the caller's transaction.

    Deliberately does NOT commit: the caller commits the audited mutation and
    this row together, so a change can never land without its trail (and a
    failed audit insert rolls the mutation back).
    """
    db.add(
        AdminAuditLog(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
        )
    )


async def list_audit_log(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    action: str | None = None,
) -> tuple[int, list[AdminAuditLogItem]]:
    base = select(AdminAuditLog, User.username).outerjoin(
        User, AdminAuditLog.actor_id == User.id
    )
    count_base = select(func.count()).select_from(AdminAuditLog)

    if action:
        base = base.where(AdminAuditLog.action == action)
        count_base = count_base.where(AdminAuditLog.action == action)

    total = (await db.execute(count_base)).scalar_one()

    query = (
        base.order_by(AdminAuditLog.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    result = await db.execute(query)

    items = [
        AdminAuditLogItem(
            id=row.id,
            actor_id=row.actor_id,
            actor_username=username,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            detail=row.detail,
            created_at=row.created_at,
        )
        for row, username in result.all()
    ]
    return total, items


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
