import json
import logging
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Date, and_, case, cast, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.annotation import Annotation
from app.models.chat import ChatMessage, ChatSession
from app.models.source import SourceSuggestion
from app.models.user import ReadingHistory, User
from app.schemas.admin import AdminAnnotationItem, AdminOverview, DailyCount

logger = logging.getLogger(__name__)

OVERVIEW_CACHE_KEY = "admin:stats:overview"
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


async def _cache_get(redis, key: str) -> dict | None:
    if redis is None:
        return None
    try:
        raw = await redis.get(key)
        if raw and isinstance(raw, str):
            return json.loads(raw)
    except Exception:
        logger.debug("Cache miss/error for key=%s", key)
    return None


async def _cache_set(redis, key: str, value: dict, ttl: int = OVERVIEW_CACHE_TTL) -> None:
    if redis is None:
        return
    try:
        await redis.setex(key, ttl, json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        logger.debug("Cache set error for key=%s", key)


async def get_trends(db: AsyncSession, days: int = 30) -> dict:
    today = _local_today()
    since = today - timedelta(days=days - 1)
    since_dt = _local_midnight_utc(since)
    date_grid = [since + timedelta(days=i) for i in range(days)]

    registrations = await _daily_counts(db, User, User.created_at, since_dt, date_grid)
    messages = await _daily_counts(db, ChatMessage, ChatMessage.created_at, since_dt, date_grid)
    active_users = await _daily_active_users(db, since_dt, date_grid)

    return {
        "registrations": registrations,
        "messages": messages,
        "active_users": active_users,
    }


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
    """Active users = distinct users who sent chat messages OR read texts each day."""
    chat_day = _local_day(ChatSession.created_at)
    read_day = _local_day(ReadingHistory.last_read_at)

    chat_q = (
        select(chat_day.label("day"), ChatSession.user_id.label("uid"))
        .where(ChatSession.created_at >= since, ChatSession.user_id.is_not(None))
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
