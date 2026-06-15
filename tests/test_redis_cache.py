from unittest.mock import AsyncMock, patch

import pytest

from app.core.redis_client import RedisCache


class TestRedisCache:
    @pytest.mark.asyncio
    @patch("app.core.redis_client.get_redis_client")
    async def test_get_json_returns_none_when_no_client(self, mock_client):
        mock_client.return_value = None
        result = await RedisCache.get_json("test_key")
        assert result is None

    @pytest.mark.asyncio
    @patch("app.core.redis_client.get_redis_client")
    async def test_get_json_returns_parsed_dict(self, mock_client):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = '{"a": 1}'
        mock_client.return_value = mock_redis
        result = await RedisCache.get_json("test_key")
        assert result == {"a": 1}

    @pytest.mark.asyncio
    @patch("app.core.redis_client.get_redis_client")
    async def test_get_json_returns_none_for_empty(self, mock_client):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_client.return_value = mock_redis
        result = await RedisCache.get_json("test_key")
        assert result is None

    @pytest.mark.asyncio
    @patch("app.core.redis_client.get_redis_client")
    async def test_set_json_calls_set_with_json(self, mock_client):
        mock_redis = AsyncMock()
        mock_redis.setex.return_value = True
        mock_client.return_value = mock_redis
        result = await RedisCache.set_json("key", {"b": 2}, 600)
        assert result is True
        mock_redis.setex.assert_called_once_with("key", 600, '{"b": 2}')

    @pytest.mark.asyncio
    @patch("app.core.redis_client.get_redis_client")
    async def test_get_returns_none_no_client(self, mock_client):
        mock_client.return_value = None
        result = await RedisCache.get("test")
        assert result is None

    @pytest.mark.asyncio
    @patch("app.core.redis_client.get_redis_client")
    async def test_set_returns_false_no_client(self, mock_client):
        mock_client.return_value = None
        result = await RedisCache.set("test", "val")
        assert result is False

    @pytest.mark.asyncio
    @patch("app.core.redis_client.get_redis_client")
    async def test_delete_returns_false_no_client(self, mock_client):
        mock_client.return_value = None
        result = await RedisCache.delete("test")
        assert result is False

    @pytest.mark.asyncio
    @patch("app.core.redis_client.get_redis_client")
    async def test_get_returns_value(self, mock_client):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "hello"
        mock_client.return_value = mock_redis
        result = await RedisCache.get("test")
        assert result == "hello"

    @pytest.mark.asyncio
    @patch("app.core.redis_client.get_redis_client")
    async def test_set_returns_true(self, mock_client):
        mock_redis = AsyncMock()
        mock_redis.setex.return_value = True
        mock_client.return_value = mock_redis
        result = await RedisCache.set("test", "val", 300)
        assert result is True
        mock_redis.setex.assert_called_once_with("test", 300, "val")

    @pytest.mark.asyncio
    @patch("app.core.redis_client.get_redis_client")
    async def test_delete_returns_true(self, mock_client):
        mock_redis = AsyncMock()
        mock_redis.delete.return_value = 1
        mock_client.return_value = mock_redis
        result = await RedisCache.delete("test")
        assert result is True
        mock_redis.delete.assert_called_once_with("test")
