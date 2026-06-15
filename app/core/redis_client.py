import asyncio
import logging

import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis_client: redis.Redis | None = None
_redis_lock = asyncio.Lock()


async def get_redis_client() -> redis.Redis:
    global _redis_client

    if _redis_client is not None:
        return _redis_client

    async with _redis_lock:
        if _redis_client is not None:
            return _redis_client
        try:
            redis_url = getattr(settings, 'REDIS_URL', None)
            if not redis_url:
                logger.warning("REDIS_URL not configured, using fallback cache")
                return None

            pool = redis.ConnectionPool.from_url(
                redis_url,
                max_connections=20,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            _redis_client = redis.Redis(
                connection_pool=pool,
                encoding="utf-8",
                decode_responses=True,
            )
            await _redis_client.ping()
            logger.info("Redis connection established")
        except Exception:
            logger.exception("Failed to connect to Redis")
            _redis_client = None

    return _redis_client


async def close_redis_client():
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis connection closed")


class RedisCache:
    @staticmethod
    async def get(key: str) -> str | None:
        client = await get_redis_client()
        if client is None:
            return None
        try:
            return await client.get(key)
        except Exception:
            logger.exception(f"Redis GET error for {key}")
            return None

    @staticmethod
    async def set(key: str, value: str, ttl_seconds: int = 300) -> bool:
        client = await get_redis_client()
        if client is None:
            return False
        try:
            await client.setex(key, ttl_seconds, value)
            return True
        except Exception:
            logger.exception(f"Redis SET error for {key}")
            return False

    @staticmethod
    async def delete(key: str) -> bool:
        client = await get_redis_client()
        if client is None:
            return False
        try:
            await client.delete(key)
            return True
        except Exception:
            logger.exception(f"Redis DELETE error for {key}")
            return False

    @staticmethod
    async def get_json(key: str) -> dict | None:
        value = await RedisCache.get(key)
        if value:
            import json
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return None
        return None

    @staticmethod
    async def set_json(key: str, value: dict, ttl_seconds: int = 300) -> bool:
        import json
        return await RedisCache.set(key, json.dumps(value), ttl_seconds)
