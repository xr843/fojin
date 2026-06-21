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

import logging
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
        "top_search_keywords": [],
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

    event_sql = text(
        """
        SELECT event_name, count(*) AS cnt
        FROM website_event
        WHERE created_at > now() - make_interval(days => :days)
          AND event_name IS NOT NULL
        GROUP BY event_name
        ORDER BY cnt DESC
        """
    )

    keyword_sql = text(
        """
        SELECT ed.string_value AS keyword, count(*) AS cnt
        FROM event_data ed
        JOIN website_event we ON we.event_id = ed.website_event_id
        WHERE we.event_name = 'search'
          AND ed.data_key = 'keyword'
          AND we.created_at > now() - make_interval(days => :days)
        GROUP BY ed.string_value
        ORDER BY cnt DESC
        LIMIT 10
        """
    )

    async with AsyncSession(engine) as session:
        event_rows = (await session.execute(event_sql, {"days": days})).all()
        keyword_rows = (await session.execute(keyword_sql, {"days": days})).all()

    counts = {row[0]: int(row[1]) for row in event_rows}

    # Module-usage board: every tracked event EXCEPT the quality signals.
    events = [
        {
            "event_name": name,
            "label": _EVENT_LABELS.get(name, name),
            "count": cnt,
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
        "top_search_keywords": top_search_keywords,
        "answer_quality": answer_quality,
    }
