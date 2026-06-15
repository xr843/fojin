from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    # Pool back to 10+20 (max 30 connections). The two streaming session-holds
    # that forced the temporary 30+90 inflation are both gone now:
    #  - /chat/stream no longer takes get_db/get_optional_user (see
    #    send_message_stream);
    #  - /exports/* (export_metadata_csv / export_kg_json / export_kg_jsonld) now
    #    fetch each keyset batch in a short-lived per-batch session and drop the
    #    unused get_optional_user dep, so they no longer pin a request-scoped
    #    connection across a slow multi-MB download (see exports._fetch_batch).
    # 30+90 also over-committed the server: max_connections is 100 and umami
    # shares this Postgres, so a fully-saturated app pool could starve umami /
    # migrations / admin scripts. 10+20 leaves comfortable headroom
    # (project_fojin_db_pool_streaming).
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
    # Per-connection guards (asyncpg GUCs). These apply ONLY to the app's
    # request connections — alembic migrations and admin scripts use their own
    # engines, so long maintenance (e.g. building a GIN index) is unaffected.
    # statement_timeout caps any single web query so a slow query can't hold a
    # pooled connection hostage and exhaust the pool — the failure mode behind
    # the 2026-06-14 incident, where un-indexed ILIKE content searches ran 60s+
    # and piled up to max_connections. 30s is far above any legitimate web query
    # (search is sub-second). idle_in_transaction guards against leaked
    # transactions. See docs/mitra-alignment-integration.md.
    connect_args={
        "server_settings": {
            "statement_timeout": "30000",
            "idle_in_transaction_session_timeout": "60000",
        }
    },
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session
