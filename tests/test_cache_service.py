from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.cache_service import CacheService


class TestCacheService:
    def test_generate_key_single(self):
        assert CacheService.generate_key("stock", "AAPL") == "stock:AAPL"

    def test_generate_key_multi(self):
        assert CacheService.generate_key("hist", "MSFT", "2024") == "hist:MSFT:2024"

    @pytest.mark.asyncio
    @patch("app.services.cache_service.REDIS_AVAILABLE", True)
    @patch("app.services.cache_service.RedisCache.get_json")
    async def test_get_redis_hit(self, mock_get_json):
        mock_get_json.return_value = {"price": 180.5}
        result = await CacheService.get(None, "stock", "AAPL")
        assert result == {"price": 180.5}

    @pytest.mark.asyncio
    @patch("app.services.cache_service.REDIS_AVAILABLE", True)
    @patch("app.services.cache_service.RedisCache.get_json")
    async def test_get_redis_miss(self, mock_get_json):
        mock_get_json.return_value = None
        result = await CacheService.get(None, "stock", "UNKNOWN")
        assert result is None

    @pytest.mark.asyncio
    @patch("app.services.cache_service.REDIS_AVAILABLE", True)
    @patch("app.services.cache_service.RedisCache.set")
    async def test_set_redis_success(self, mock_set):
        mock_set.return_value = True
        result = await CacheService.set(None, "stock", "AAPL", value={"price": 180.5})
        assert result is True

    @pytest.mark.asyncio
    @patch("app.services.cache_service.REDIS_AVAILABLE", True)
    @patch("app.services.cache_service.RedisCache.set")
    async def test_set_redis_success_string_value(self, mock_set):
        mock_set.return_value = True
        result = await CacheService.set(None, "str", "key", value="plain_string")
        assert result is True

    @pytest.mark.asyncio
    @patch("app.services.cache_service.REDIS_AVAILABLE", True)
    @patch("app.services.cache_service.RedisCache.set")
    async def test_set_redis_success_json_string(self, mock_set):
        mock_set.return_value = True
        result = await CacheService.set(None, "json", "key", value='{"a":1}')
        assert result is True

    @pytest.mark.asyncio
    @patch("app.services.cache_service.REDIS_AVAILABLE", True)
    @patch("app.services.cache_service.RedisCache.set")
    async def test_set_redis_success_list_value(self, mock_set):
        mock_set.return_value = True
        result = await CacheService.set(None, "list", "key", value=[1, 2, 3])
        assert result is True

    @pytest.mark.asyncio
    @patch("app.services.cache_service.REDIS_AVAILABLE", True)
    @patch("app.services.cache_service.RedisCache.set")
    async def test_set_redis_failure_fallback(self, mock_set):
        mock_set.return_value = False
        with patch("app.services.cache_service.CacheService._set_postgres",
                   new_callable=AsyncMock, return_value=True):
            result = await CacheService.set(None, "stock", "AAPL", value={"price": 180.5})
            assert result is True

    @pytest.mark.asyncio
    @patch("app.services.cache_service.REDIS_AVAILABLE", False)
    @patch("app.services.cache_service.RedisCache.set")
    async def test_set_no_redis(self, mock_set):
        with patch("app.services.cache_service.CacheService._set_postgres",
                   new_callable=AsyncMock, return_value=True):
            result = await CacheService.set(None, "stock", "AAPL", value={"price": 180.5})
            assert result is True
            mock_set.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.services.cache_service.REDIS_AVAILABLE", True)
    @patch("app.services.cache_service.RedisCache.delete")
    async def test_delete_redis(self, mock_delete):
        mock_delete.return_value = True
        with patch("app.services.cache_service.CacheService._delete_postgres",
                   new_callable=AsyncMock, return_value=True):
            result = await CacheService.delete(None, "stock", "AAPL")
            assert result is True

    @pytest.mark.asyncio
    @patch("app.services.cache_service.REDIS_AVAILABLE", False)
    @patch("app.services.cache_service.RedisCache.get_json")
    async def test_get_no_redis_available(self, mock_get_json):
        result = await CacheService.get(None, "stock", "MSFT")
        assert result is None
        mock_get_json.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.services.cache_service.REDIS_AVAILABLE", False)
    @patch("app.services.cache_service.RedisCache.delete")
    async def test_delete_no_redis(self, mock_delete):
        with patch("app.services.cache_service.CacheService._delete_postgres",
                   new_callable=AsyncMock, return_value=True):
            result = await CacheService.delete(None, "stock", "AAPL")
            assert result is True
            mock_delete.assert_not_called()

    def test_generate_key_empty_parts(self):
        assert CacheService.generate_key("test") == "test:"

    def test_generate_key_numeric_parts(self):
        assert CacheService.generate_key("user", 42) == "user:42"
