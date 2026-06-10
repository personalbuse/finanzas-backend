from sqlalchemy import text

from app.models.base import Base


async def init_db():
    from app.db.session import engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def check_connection():
    from app.db.session import engine
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        return result.scalar() == 1
