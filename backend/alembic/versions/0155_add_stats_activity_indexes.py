"""add btree indexes for stats/activity aggregation hot columns

Revision ID: 0155
Revises: 0154
Create Date: 2026-06-13

The dashboard/stats and activity endpoints (services/stats_service.py) run
GROUP-BY aggregations and date-range filters over the largest / fastest-growing
tables, but the filtered columns had no indexes — so a cache-cold refresh
sequentially scanned the whole table. Caching (overview 1h, activity 5min)
hides this most of the time; these indexes cut the cold-refresh cost.

Verified query sites in stats_service.py:
  - buddhist_texts.dynasty   GROUP BY + WHERE is_not(None) (:73-75) + timeline filter (:177)
  - buddhist_texts.category  GROUP BY + WHERE is_not(None) (:100-102) + timeline filter (:181)
  - buddhist_texts.created_at  WHERE >= cutoff (:389)
  - reading_history.last_read_at  WHERE >= cutoff (:319,326,338)
  - chat_messages.created_at   WHERE >= cutoff (:351,367)
  - chat_sessions.created_at   WHERE >= cutoff (:357)
  - users.created_at           WHERE >= cutoff (:376)
  - users.last_active_at       WHERE >= cutoff (:382)

CREATE INDEX IF NOT EXISTS keeps this idempotent/safe. Plain (non-CONCURRENT)
builds are fine here: these tables are small-to-moderate and the migration
runs during the deploy restart window. lang is intentionally skipped — only
~6 distinct values, the planner won't use a btree for it.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0155"
down_revision: str | None = "0154"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEXES = [
    ("ix_buddhist_texts_dynasty", "buddhist_texts", "dynasty"),
    ("ix_buddhist_texts_category", "buddhist_texts", "category"),
    ("ix_buddhist_texts_created_at", "buddhist_texts", "created_at"),
    ("ix_reading_history_last_read_at", "reading_history", "last_read_at"),
    ("ix_chat_messages_created_at", "chat_messages", "created_at"),
    ("ix_chat_sessions_created_at", "chat_sessions", "created_at"),
    ("ix_users_created_at", "users", "created_at"),
    ("ix_users_last_active_at", "users", "last_active_at"),
]


def upgrade() -> None:
    for name, table, column in INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({column})")


def downgrade() -> None:
    for name, _table, _column in INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
