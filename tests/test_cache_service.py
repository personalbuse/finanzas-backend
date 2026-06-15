from unittest.mock import AsyncMock, MagicMock, patch

from app.services.cache_service import CacheService


class TestCacheService:
    def test_generate_key_single(self):
        assert CacheService.generate_key("stock", "AAPL") == "stock:AAPL"

    def test_generate_key_multi(self):
        assert CacheService.generate_key("hist", "MSFT", "2024") == "hist:MSFT:2024"

    @patch("app.services.cache_service.REDIS_AVAILABLE", True)
    @patch("app.services.cache_service.RedisCache.get_json")
    async def test_get_redis_hit(self, mock_get_json):
        mock_get_json.return_value = {"price": 180.5}
        result = await CacheService.get(None, "stock", "AAPL")
        assert result == {"price": 180.5}

    @patch("app.services.cache_service.REDIS_AVAILABLE", True)
    @patch("app.services.cache_service.RedisCache.get_json")
    async def test_get_redis_miss(self, mock_get_json):
        mock_get_json.return_value = None
        result = await CacheService.get(None, "stock", "UNKNOWN")
        assert result is None

    @patch("app.services.cache_service.REDIS_AVAILABLE", True)
    @patch("app.services.cache_service.RedisCache.set")
    async def test_set_redis_success(self, mock_set):
        mock_set.return_value = True
        result = await CacheService.set(None, "stock", "AAPL", value={"price": 180.5})
        assert result is True

    @patch("app.services.cache_service.REDIS_AVAILABLE", True)
    @patch("app.services.cache_service.RedisCache.set")
    async def test_set_redis_failure_fallback(self, mock_set):
        mock_set.return_value = False
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=None)
        with patch("app.db.session.AsyncSessionLocal", return_value=mock_session_ctx):
            result = await CacheService.set(None, "stock", "AAPL", value={"price": 180.5})
            assert result is True
            mock_session.commit.assert_awaited_once()

    @patch("app.services.cache_service.REDIS_AVAILABLE", True)
    @patch("app.services.cache_service.RedisCache.delete")
    async def test_delete_redis(self, mock_delete):
        mock_delete.return_value = True
        result = await CacheService.delete(None, "stock", "AAPL")
        assert result is False
