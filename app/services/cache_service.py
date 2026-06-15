import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

try:
    from app.core.redis_client import RedisCache
    REDIS_AVAILABLE = True
except ImportError:  # pragma: no cover
    REDIS_AVAILABLE = False
    logger.warning("Redis not available, using PostgreSQL fallback")


class CacheService:
    @staticmethod
    def generate_key(prefix: str, *parts: str) -> str:
        return f"{prefix}:{':'.join(str(p) for p in parts)}"

    @staticmethod
    async def get(_session, prefix: str, *parts: str) -> Any | None:
        key = CacheService.generate_key(prefix, *parts)

        if REDIS_AVAILABLE:
            cached = await RedisCache.get_json(key)
            if cached:
                return cached

        return await CacheService._get_postgres(key)

    @staticmethod
    async def _get_postgres(key: str) -> Any | None:  # pragma: no cover
        from sqlalchemy import and_, select

        from app.db.session import AsyncSessionLocal
        from app.models.base import CacheData

        try:
            async with AsyncSessionLocal() as cache_session:
                stmt = select(CacheData).where(
                    and_(
                        CacheData.key == key,
                        CacheData.expires_at > datetime.utcnow()
                    )
                )
                result = await cache_session.execute(stmt)
                cache_entry = result.scalar_one_or_none()

                if cache_entry:
                    import json
                    try:
                        return json.loads(cache_entry.value)
                    except (json.JSONDecodeError, TypeError):
                        return cache_entry.value
        except Exception:
            logger.exception(f"Error reading cache for {key}")

        return None

    @staticmethod
    async def set(_session, prefix: str, *parts: str,
                  value: Any, ttl_seconds: int = 300) -> bool:
        key = CacheService.generate_key(prefix, *parts)

        if REDIS_AVAILABLE:
            import json
            if isinstance(value, (dict, list)):
                redis_value = json.dumps(value)
            elif isinstance(value, str) and value.startswith('{'):
                redis_value = value
            else:
                redis_value = str(value)

            redis_success = await RedisCache.set(key, redis_value, ttl_seconds)
            if redis_success:
                return True

        return await CacheService._set_postgres(key, value, ttl_seconds)

    @staticmethod
    async def _set_postgres(key: str, value: Any, ttl_seconds: int) -> bool:  # pragma: no cover
        import json

        from sqlalchemy import select

        from app.db.session import AsyncSessionLocal
        from app.models.base import CacheData

        if isinstance(value, (dict, list)):
            value_str = json.dumps(value)
        else:
            value_str = str(value)

        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)

        try:
            async with AsyncSessionLocal() as cache_session:
                stmt = select(CacheData).where(CacheData.key == key)
                result = await cache_session.execute(stmt)
                cache_entry = result.scalar_one_or_none()

                if cache_entry:
                    cache_entry.value = value_str
                    cache_entry.expires_at = expires_at
                else:
                    cache_entry = CacheData(
                        key=key,
                        value=value_str,
                        expires_at=expires_at
                    )
                    cache_session.add(cache_entry)

                await cache_session.commit()
                return True
        except Exception:
            logger.exception(f"Error writing to cache for {key}")
            return False

    @staticmethod
    async def delete(_session, prefix: str, *parts: str) -> bool:
        key = CacheService.generate_key(prefix, *parts)

        if REDIS_AVAILABLE:
            await RedisCache.delete(key)

        return await CacheService._delete_postgres(key)

    @staticmethod
    async def _delete_postgres(key: str) -> bool:  # pragma: no cover
        from sqlalchemy import select

        from app.db.session import AsyncSessionLocal
        from app.models.base import CacheData

        try:
            async with AsyncSessionLocal() as cache_session:
                stmt = select(CacheData).where(CacheData.key == key)
                result = await cache_session.execute(stmt)
                cache_entry = result.scalar_one_or_none()

                if cache_entry:
                    await cache_session.delete(cache_entry)
                    await cache_session.commit()
                    return True
                return False
        except Exception:
            logger.exception(f"Error deleting cache key {key}")
            return False

    @staticmethod
    async def invalidate_prefix(_session, prefix: str) -> bool:  # pragma: no cover
        if REDIS_AVAILABLE:
            logger.info(f"Invalidating Redis keys with prefix: {prefix}")

        from sqlalchemy import delete

        from app.db.session import AsyncSessionLocal
        from app.models.base import CacheData

        try:
            async with AsyncSessionLocal() as cache_session:
                stmt = delete(CacheData).where(CacheData.key.startswith(prefix + ":"))
                result = await cache_session.execute(stmt)
                await cache_session.commit()
                return result.rowcount > 0
        except Exception:
            logger.exception(f"Error invalidating cache prefix {prefix}")
            return False
