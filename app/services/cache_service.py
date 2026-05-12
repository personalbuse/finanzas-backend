import logging
from typing import Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

try:
    from app.core.redis_client import RedisCache
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available, using PostgreSQL fallback")


class CacheService:
    @staticmethod
    def generate_key(prefix: str, *parts: str) -> str:
        return f"{prefix}:{':'.join(str(p) for p in parts)}"
    
    @staticmethod
    async def get(session, prefix: str, *parts: str) -> Optional[Any]:
        key = CacheService.generate_key(prefix, *parts)
        
        if REDIS_AVAILABLE:
            cached = await RedisCache.get_json(key)
            if cached:
                logger.info(f"Redis cache hit for {key}")
                return cached
        
        from sqlalchemy import select, and_
        from app.models.base import CacheData
        
        stmt = select(CacheData).where(
            and_(
                CacheData.key == key,
                CacheData.expires_at > datetime.utcnow()
            )
        )
        result = await session.execute(stmt)
        cache_entry = result.scalar_one_or_none()
        
        if cache_entry:
            import json
            try:
                return json.loads(cache_entry.value)
            except (json.JSONDecodeError, TypeError):
                return cache_entry.value
        
        return None
    
    @staticmethod
    async def set(session, prefix: str, *parts: str, 
                  value: Any, ttl_seconds: int = 300) -> bool:
        key = CacheService.generate_key(prefix, *parts)
        
        if REDIS_AVAILABLE:
            import json
            if isinstance(value, (dict, list)):
                value_str = json.dumps(value)
            else:
                value_str = str(value)
            
            redis_success = await RedisCache.set_json(key, value if isinstance(value, dict) else json.loads(value) if isinstance(value_str, str) and value_str.startswith('{') else value, ttl_seconds)
            if redis_success:
                logger.info(f"Redis cache set for {key}")
                return True
        
        from sqlalchemy import select
        from app.models.base import CacheData
        import json
        
        if isinstance(value, (dict, list)):
            value_str = json.dumps(value)
        else:
            value_str = str(value)
        
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        
        try:
            stmt = select(CacheData).where(CacheData.key == key)
            result = await session.execute(stmt)
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
                session.add(cache_entry)
            
            await session.commit()
            logger.info(f"PostgreSQL cache set for {key}")
            return True
        except Exception as e:
            await session.rollback()
            logger.exception(f"Error writing to cache for {key}")
            return False
    
    @staticmethod
    async def delete(session, prefix: str, *parts: str) -> bool:
        key = CacheService.generate_key(prefix, *parts)
        
        if REDIS_AVAILABLE:
            await RedisCache.delete(key)
        
        from sqlalchemy import select, delete
        from app.models.base import CacheData
        
        stmt = select(CacheData).where(CacheData.key == key)
        result = await session.execute(stmt)
        cache_entry = result.scalar_one_or_none()
        
        if cache_entry:
            await session.delete(cache_entry)
            await session.commit()
            return True
        return False
    
    @staticmethod
    async def invalidate_prefix(session, prefix: str) -> bool:
        if REDIS_AVAILABLE:
            logger.info(f"Invalidating Redis keys with prefix: {prefix}")
        
        from sqlalchemy import delete
        from app.models.base import CacheData
        
        stmt = delete(CacheData).where(CacheData.key.startswith(prefix + ":"))
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount > 0