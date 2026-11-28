"""Module usage service — reads from the self-hosted Umami analytics database.

The Umami DB lives on the SAME postgres server as the fojin app DB, using the
same credentials but a different database name ("umami").  We derive its URL
by replacing the last path segment of settings.database_url.

Design goals:
- Lazy singleton engine: created on first call, NOT at app startup, so a
  missing/unreachable Umami DB never prevents the app from booting.
- Full resilience: every public function catches ALL exceptions from the Umami
  DB, logs a warning, and returns safe zero/empty defaults.  The admin
  dashboard must never 500 due to Umami being down.
- Safe parametrisation: the `days` window is bound via SQLAlchemy text() with
  a named param — never string-interpolated.
"""

import hashlib
import logging
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import settings

logger = logging.getLogger(__name__)

# Lazy singleton — None until first successful call to _get_engine().
_umami_engine = None

# Friendly Chinese labels for known Umami event_name values.
_EVENT_LABELS: dict[str, str] = {
    "search": "检索",
    "chat": "AI问答",
    "read": "在线阅读",
    "source_click": "数据源点击",
    "cbeta-shortcut": "CBETA直跳",
}

# Behavioural answer-quality signals. Tracked as Umami events on every chat
# answer (not just the ~0% that get an explicit 👍/👎), so they give a quality
# proxy with real volume. Pulled OUT of the module-usage `events` list so they
# don't clutter the "板块使用情况" board, and reported as rates against the
# number of questions asked (the `chat` event).
_QUALITY_EVENTS: tuple[str, ...] = ("citation_click", "chat_copy", "chat_retry")


# 登录用户代号：与 frontend/src/analyticsSignals.ts 的 memberCode 同一算法同一盐——改一边必须改另一边，
# 否则后台再也对不上账号。SHA-256("<用户 id>|<盐>") 的前 16 个十六进制字符。
MEMBER_SALT = "fojin-umami-member-2026-11"
# 代号从这天起才上报（#1577）；之前的日期按账号的辞典 / 佛教史 / 检索次数无从统计。
MEMBER_TRACKING_SINCE = date(2026, 11, 28)

# 路径 → 板块，与 analyticsSignals.ts 的 sectionOf 一致。
_SECTION_SQL = """
    CASE
        WHEN {p} LIKE '/chat%' OR {p} LIKE '/share/qa%' THEN 'chat'
        WHEN {p} ~ '^/texts/[0-9]+/read' OR {p} = '/read' OR {p} LIKE '/read-aloud%' THEN 'read'
        WHEN {p} LIKE '/texts%' THEN 'texts'
        WHEN {p} LIKE '/dictionary%' OR {p} LIKE '/dict/%' THEN 'dict'
        WHEN {p} LIKE '/sources%' THEN 'sources'
        WHEN {p} LIKE '/history%' THEN 'history'
        WHEN {p} LIKE '/kg%' THEN 'kg'
        WHEN {p} LIKE '/search%' THEN 'search'
        WHEN {p} LIKE '/daily%' THEN 'daily'
        WHEN {p} = '/' THEN 'home'
        ELSE 'other'
    END
"""

# 板块总览只数「有人动手」的事件：自动出现的（*_show / *_shown）、网络重试、出错、有效访问信号都不算使用。
_PASSIVE_EVENT_SQL = """
    (event_name LIKE '%\\_show' OR event_name LIKE '%\\_shown' OR event_name LIKE 'api\\_%'
     OR event_name LIKE '%error%' OR event_name LIKE 'chat\\_session\\_load%'
     OR event_name IN ('engaged', 'chat_recovered'))
"""


def member_code(user_id: int) -> str:
    return hashlib.sha256(f"{user_id}|{MEMBER_SALT}".encode()).hexdigest()[:16]


async def member_section_views(start: datetime, end: datetime) -> dict[str, dict[str, int]]:
    """[start, end) 内登录用户（按代号）在各板块的浏览次数：{代号: {板块: 次数}}。Umami 不可用时返回空。"""
    sql = text(
        f"""
        SELECT s.distinct_id, {_SECTION_SQL.format(p="e.url_path")} AS section, count(*)
        FROM website_event e
        JOIN session s ON s.session_id = e.session_id
        WHERE e.website_id IN (SELECT website_id FROM website WHERE domain = :domain AND deleted_at IS NULL)
          AND e.event_type = 1
          AND e.created_at >= :start AND e.created_at < :end
          AND s.distinct_id IS NOT NULL
        GROUP BY 1, 2
        """
    )
    try:
        async with AsyncSession(_get_engine()) as session:
            rows = (
                await session.execute(sql, {"domain": settings.umami_site_domain, "start": start, "end": end})
            ).all()
    except Exception as exc:
        logger.warning("Umami DB unavailable — no per-member section views: %s", exc)
        return {}
    out: dict[str, dict[str, int]] = {}
    for code, section, n in rows:
        out.setdefault(code, {})[section] = int(n)
    return out


def _build_umami_url() -> str:
    """Derive the Umami async DB URL from the fojin app DB URL.

    The fojin URL looks like:
        postgresql+asyncpg://user:pass@host:5432/fojin

    We replace the last path segment ("fojin") with "umami".
    """
    base, _db = settings.database_url.rsplit("/", 1)
    return f"{base}/umami"


def _get_engine():
    """Return (or lazily create) the Umami engine singleton."""
    global _umami_engine
    if _umami_engine is None:
        url = _build_umami_url()
        _umami_engine = create_async_engine(
            url,
            # Keep pool small — this is a side-channel analytics DB.
            pool_size=2,
            max_overflow=3,
            pool_pre_ping=True,
            # Don't hold connections open indefinitely if Umami goes down.
            pool_recycle=300,
        )
        logger.info("Umami engine created: %s", url.split("@")[-1])  # log host/db only
    return _umami_engine


async def get_module_usage(days: int = 7) -> dict[str, Any]:
    """Return event counts and top search keywords from the Umami DB.

    Args:
        days: Time window in days (1–90).  Parametrised safely via bound param.

    Returns a dict with:
        events: list of {event_name, label, count}  — sorted descending by count
        top_search_keywords: list of {keyword, count}  — top 10 by count

    On any Umami DB error, logs a warning and returns safe empty defaults so
    that the admin dashboard never 500 because Umami is unavailable.
    """
    try:
        return await _query_module_usage(days)
    except Exception as exc:
        logger.warning(
            "Umami DB unavailable — returning empty module usage (days=%d): %s",
            days,
            exc,
        )
        return _empty_usage()


def _empty_usage() -> dict[str, Any]:
    return {
        "events": [],
        "sections": [],
        "members_since": MEMBER_TRACKING_SINCE.isoformat(),
        "top_search_keywords": [],
        "excluded_staff_events": 0,
        "answer_quality": {
            "chat_questions": 0,
            "citation_click": 0,
            "chat_copy": 0,
            "chat_retry": 0,
            "citation_click_rate": None,
            "copy_rate": None,
            "retry_rate": None,
        },
    }


async def _query_module_usage(days: int) -> dict[str, Any]:
    engine = _get_engine()

    # 口径（与到期复查脚本、baidu_priority.sql 一致）：
    # - 只算 fojin 的站点行：同一 Umami 实例还托管别的站（11-24 昆虫站事件占这块看板 73%）；
    # - 去掉站长本人：近期访问过 /admin 的设备（11-24 实测 trace_done 72 次里 49 次是站长自测）；
    # - 去掉本机开发（hostname = localhost / 127.0.0.1）。
    base_cte = """
        WITH site AS (
            SELECT website_id FROM website WHERE domain = :domain AND deleted_at IS NULL
        ),
        staff AS (
            SELECT DISTINCT session_id FROM website_event
            WHERE website_id IN (SELECT website_id FROM site)
              AND url_path LIKE '/admin%'
              AND created_at > now() - make_interval(days => :days + 30)
        ),
        ev AS (
            -- 游客用完免费次数也打 chat_stream_error（reason=quota），但那是正常的额度提示、不是故障：
            -- 改记成 chat_quota_hit，看板上单列，不再算进「异常」（2026-11-28：7 天 80 次里占 7 次）。
            SELECT e.event_id,
                   CASE WHEN e.event_name = 'chat_stream_error' AND EXISTS (
                            SELECT 1 FROM event_data q
                            WHERE q.website_event_id = e.event_id AND q.data_key = 'reason' AND q.string_value = 'quota'
                        ) THEN 'chat_quota_hit' ELSE e.event_name END AS event_name,
                   e.session_id,
                   (e.session_id IN (SELECT session_id FROM staff)
                    OR coalesce(e.hostname, '') IN ('localhost', '127.0.0.1')) AS is_staff
            FROM website_event e
            WHERE e.website_id IN (SELECT website_id FROM site)
              AND e.created_at > now() - make_interval(days => :days)
              AND e.event_name IS NOT NULL
        )
    """

    event_sql = text(
        base_cte
        + """
        SELECT event_name,
               count(*) FILTER (WHERE NOT is_staff) AS cnt,
               count(DISTINCT session_id) FILTER (WHERE NOT is_staff) AS users,
               count(*) FILTER (WHERE is_staff) AS staff_cnt
        FROM ev
        GROUP BY event_name
        ORDER BY cnt DESC
        """
    )

    keyword_sql = text(
        base_cte
        + """
        SELECT btrim(ed.string_value) AS keyword, count(*) AS cnt
        FROM event_data ed
        JOIN ev ON ev.event_id = ed.website_event_id
        WHERE ev.event_name = 'search'
          AND NOT ev.is_staff
          AND ed.data_key = 'keyword'
        GROUP BY btrim(ed.string_value)
        ORDER BY cnt DESC
        LIMIT 10
        """
    )

    # 板块总览：本周期与上一周期（等长）各板块「动手的人 / 次数」，外加登录用户数（按代号，11-28 起）。
    sections_sql = text(
        f"""
        WITH site AS (
            SELECT website_id FROM website WHERE domain = :domain AND deleted_at IS NULL
        ),
        staff AS (
            SELECT DISTINCT session_id FROM website_event
            WHERE website_id IN (SELECT website_id FROM site)
              AND url_path LIKE '/admin%'
              AND created_at > now() - make_interval(days => :days * 2 + 30)
        ),
        ev AS (
            SELECT {_SECTION_SQL.format(p="e.url_path")} AS section, e.session_id, e.event_type, e.event_name,
                   e.created_at > now() - make_interval(days => :days) AS cur
            FROM website_event e
            WHERE e.website_id IN (SELECT website_id FROM site)
              AND e.created_at > now() - make_interval(days => :days * 2)
              AND e.session_id NOT IN (SELECT session_id FROM staff)
              AND coalesce(e.hostname, '') NOT IN ('localhost', '127.0.0.1')
        )
        SELECT ev.section,
               count(DISTINCT ev.session_id) FILTER (WHERE cur AND event_type = 2 AND NOT {_PASSIVE_EVENT_SQL}),
               count(*) FILTER (WHERE cur AND event_type = 2 AND NOT {_PASSIVE_EVENT_SQL}),
               count(DISTINCT ev.session_id) FILTER (WHERE NOT cur AND event_type = 2 AND NOT {_PASSIVE_EVENT_SQL}),
               count(*) FILTER (WHERE NOT cur AND event_type = 2 AND NOT {_PASSIVE_EVENT_SQL}),
               count(DISTINCT s.distinct_id) FILTER (WHERE cur AND event_type = 1),
               count(*) FILTER (WHERE cur AND event_type = 1)
        FROM ev LEFT JOIN session s ON s.session_id = ev.session_id
        GROUP BY ev.section
        """
    )

    async with AsyncSession(engine) as session:
        params = {"days": days, "domain": settings.umami_site_domain}
        event_rows = (await session.execute(event_sql, params)).all()
        keyword_rows = (await session.execute(keyword_sql, params)).all()
        section_rows = (await session.execute(sections_sql, params)).all()

    sections = sorted(
        (
            {
                "section": r[0],
                "users": int(r[1]),
                "count": int(r[2]),
                "prev_users": int(r[3]),
                "prev_count": int(r[4]),
                "members": int(r[5]),
                "pageviews": int(r[6]),
            }
            for r in section_rows
        ),
        key=lambda x: (x["users"], x["count"]),
        reverse=True,
    )

    counts = {row[0]: int(row[1]) for row in event_rows if int(row[1]) > 0}
    users = {row[0]: int(row[2]) for row in event_rows}
    excluded_staff_events = sum(int(row[3]) for row in event_rows)

    # Module-usage board: every tracked event EXCEPT the quality signals.
    events = [
        {
            "event_name": name,
            "label": _EVENT_LABELS.get(name, name),
            "count": cnt,
            "users": users.get(name, 0),
        }
        for name, cnt in counts.items()
        if name not in _QUALITY_EVENTS
    ]

    # Answer-quality proxies, as rates against questions asked. Denominator is
    # the `chat` event (one per question). `None` when there is no chat volume
    # yet so the UI can show "—" instead of a misleading 0%.
    chat_n = counts.get("chat", 0)

    def _rate(n: int) -> float | None:
        return round(n / chat_n * 100, 1) if chat_n else None

    citation_click = counts.get("citation_click", 0)
    chat_copy = counts.get("chat_copy", 0)
    chat_retry = counts.get("chat_retry", 0)
    answer_quality = {
        "chat_questions": chat_n,
        "citation_click": citation_click,
        "chat_copy": chat_copy,
        "chat_retry": chat_retry,
        "citation_click_rate": _rate(citation_click),
        "copy_rate": _rate(chat_copy),
        "retry_rate": _rate(chat_retry),
    }

    top_search_keywords = [
        {"keyword": row[0], "count": int(row[1])}
        for row in keyword_rows
        if row[0]  # skip null/empty keywords
    ]

    return {
        "events": events,
        "sections": sections,
        "members_since": MEMBER_TRACKING_SINCE.isoformat(),
        "top_search_keywords": top_search_keywords,
        "answer_quality": answer_quality,
        "excluded_staff_events": excluded_staff_events,
    }
