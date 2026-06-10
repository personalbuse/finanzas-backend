from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestNewsService:
    @pytest.fixture
    def service(self):
        from app.services.news_service import NewsService
        return NewsService()

    @pytest.fixture
    def mock_http(self):
        mock = AsyncMock()
        mock.get = AsyncMock()
        mock.aclose = AsyncMock()
        return mock

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    # ─── get_news ───

    @pytest.mark.asyncio
    async def test_get_news_cached(self, service, mock_db):
        cached = [{"headline": "Cached News"}]
        with patch("app.services.news_service.CacheService.get", AsyncMock(return_value=cached)):
            result = await service.get_news(category="general", limit=3, db=mock_db)
            assert result == cached

    @pytest.mark.asyncio
    async def test_get_news_no_api_key_uses_mock(self, service, mock_db):
        service.api_key = None
        with patch("app.services.news_service.CacheService.get", AsyncMock(return_value=None)):
            result = await service.get_news(category="general", limit=2, db=mock_db)
            assert len(result) == 2
            assert result[0]["source"] == "Reuters"

    @pytest.mark.asyncio
    async def test_get_news_api_success(self, service, mock_db, mock_http):
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value=[
            {"id": 1, "headline": "Real News", "summary": "Summary here", "url": "https://example.com",
             "image": "", "source": "Bloomberg", "datetime": 1700000000, "category": "market"}
        ])
        mock_http.get = AsyncMock(return_value=mock_response)
        service.http_client = mock_http

        with patch("app.services.news_service.CacheService.get", AsyncMock(return_value=None)):
            with patch("app.services.news_service.CacheService.set", AsyncMock()) as mock_set:
                result = await service.get_news(category="market", limit=1, db=mock_db)
                assert len(result) == 1
                assert result[0]["headline"] == "Real News"
                mock_set.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_news_api_empty_falls_to_mock(self, service, mock_db, mock_http):
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value=[])
        mock_http.get = AsyncMock(return_value=mock_response)
        service.http_client = mock_http

        with patch("app.services.news_service.CacheService.get", AsyncMock(return_value=None)):
            result = await service.get_news(category="general", limit=2, db=mock_db)
            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_news_api_error_falls_to_mock(self, service, mock_db, mock_http):
        import httpx
        mock_http.get = AsyncMock(side_effect=httpx.HTTPError("API error"))
        service.http_client = mock_http

        with patch("app.services.news_service.CacheService.get", AsyncMock(return_value=None)):
            result = await service.get_news(category="general", limit=2, db=mock_db)
            assert len(result) == 2
            assert result[0]["source"] == "Reuters"

    @pytest.mark.asyncio
    async def test_get_news_no_db_no_cache(self, service, mock_http):
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value=[
            {"id": 1, "headline": "No DB", "summary": "No DB", "url": "https://example.com",
             "image": "", "source": "Bloomberg", "datetime": 1700000000, "category": "market"}
        ])
        mock_http.get = AsyncMock(return_value=mock_response)
        service.http_client = mock_http

        result = await service.get_news(category="market", limit=1, db=None)
        assert len(result) == 1

    # ─── get_news_by_symbol ───

    @pytest.mark.asyncio
    async def test_get_news_by_symbol_no_api_key(self, service):
        service.api_key = None
        result = await service.get_news_by_symbol("AAPL", limit=2)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_news_by_symbol_success(self, service, mock_http):
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value=[
            {"id": 1, "headline": "AAPL News", "summary": "Summary", "url": "https://example.com",
             "image": "", "source": "Bloomberg", "datetime": 1700000000, "category": "company"}
        ])
        mock_http.get = AsyncMock(return_value=mock_response)
        service.http_client = mock_http

        result = await service.get_news_by_symbol("AAPL", limit=1)
        assert len(result) == 1
        assert result[0]["headline"] == "AAPL News"
        assert result[0]["category"] == "company"

    @pytest.mark.asyncio
    async def test_get_news_by_symbol_not_found(self, service, mock_http):
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value="No symbol found")
        mock_http.get = AsyncMock(return_value=mock_response)
        service.http_client = mock_http

        result = await service.get_news_by_symbol("UNKNOWN", limit=2)
        assert len(result) == 2
        assert result[0]["source"] == "Reuters"

    @pytest.mark.asyncio
    async def test_get_news_by_symbol_error(self, service, mock_http):
        import httpx
        mock_http.get = AsyncMock(side_effect=httpx.HTTPError("Network error"))
        service.http_client = mock_http

        result = await service.get_news_by_symbol("AAPL", limit=2)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_news_by_symbol_empty_data(self, service, mock_http):
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value=[])
        mock_http.get = AsyncMock(return_value=mock_response)
        service.http_client = mock_http

        result = await service.get_news_by_symbol("AAPL", limit=2)
        assert len(result) == 2
