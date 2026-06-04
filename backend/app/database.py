from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    # Pool sized for streaming workload. /chat/stream is a Server-Sent
    # Events endpoint and FastAPI holds the dependency-injected session
    # for the entire stream duration (60-120s with LLM latency), so a
    # single user with 1-2 simultaneous tabs plus an SEO crawler hitting
    # /dict/* can pin the previous 10+20 budget within minutes. The
    # right long-term fix is to release the session between the prep
    # phase and the LLM-streaming phase inside `send_message_stream`;
    # until that lands, 30+90 keeps the service well clear of PG's
    # default 100-connection budget while masking the streaming-hold.
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
