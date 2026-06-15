import logging

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)

db_url = settings.DATABASE_URL
if "postgresql" in db_url and "+asyncpg" not in db_url:  # pragma: no cover
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)  # pragma: no cover
    db_url = db_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)  # pragma: no cover

engine = create_async_engine(
    db_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_timeout=30,
)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, expire_on_rollback=False)


async def get_db() -> AsyncSession:  # pragma: no cover
    async with AsyncSessionLocal() as session:
        yield session
