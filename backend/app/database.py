from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    # Pool stays at 30+90 for now. /chat/stream's streaming session-hold is
    # GONE (it no longer takes get_db/get_optional_user — see send_message_stream),
    # which removes the dominant masker. BUT the /exports/* endpoints
    # (export_metadata_csv / export_kg_json / export_kg_jsonld) still hold a
    # request-scoped get_db session across their full keyset-paginated dump
    # generators (10k+ rows) — the same streaming-hold pattern. Cutting back to
    # the pre-masking 10+20 must wait until those get the same short-lived
    # per-batch session treatment, else a few concurrent exports could exhaust
    # the pool the way chat used to (project_fojin_db_pool_streaming).
    pool_size=30,
    max_overflow=90,
    pool_pre_ping=True,
    pool_recycle=3600,
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session
