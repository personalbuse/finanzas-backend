from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestExchangeRateService:
    @pytest.fixture
    def service(self):
        from app.services.exchange_rate_service import ExchangeRateService
        return ExchangeRateService()

    @pytest.fixture
    def mock_http(self):
        mock = AsyncMock()
        mock.get = AsyncMock()
        mock.aclose = AsyncMock()
        return mock

    @pytest.fixture
    def mock_db(self):
        m = MagicMock()
        m.execute = AsyncMock()
        m.add = MagicMock()
        m.flush = AsyncMock()
        m.commit = AsyncMock()
        return m

    # ─── _fetch_rate_from_api ───

    @pytest.mark.asyncio
    async def test_fetch_rate_from_api_success(self, service, mock_http):
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value={
            "result": "success",
            "conversion_rates": {"COP": 3800.0}
        })
        mock_http.get = AsyncMock(return_value=mock_response)
        service.http_client = mock_http

        result = await service._fetch_rate_from_api("USD", "COP")
        assert result["rate"] == 3800.0
        assert result["from_currency"] == "USD"
        assert result["source"] == "ExchangeRate-API"

    @pytest.mark.asyncio
    async def test_fetch_rate_from_api_error_response(self, service, mock_http):
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value={"result": "error", "error-type": "unsupported-code"})
        mock_http.get = AsyncMock(return_value=mock_response)
        service.http_client = mock_http

        result = await service._fetch_rate_from_api("USD", "INVALID")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_rate_from_api_missing_currency(self, service, mock_http):
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value={
            "result": "success",
            "conversion_rates": {"EUR": 0.85}
        })
        mock_http.get = AsyncMock(return_value=mock_response)
        service.http_client = mock_http

        result = await service._fetch_rate_from_api("USD", "XYZ")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_rate_from_api_http_error(self, service, mock_http):
        import httpx
        mock_http.get = AsyncMock(side_effect=httpx.HTTPError("Connection error"))
        service.http_client = mock_http

        with pytest.raises(httpx.HTTPError):
            await service._fetch_rate_from_api("USD", "COP")

    # ─── _get_fallback_rate ───

    @pytest.mark.asyncio
    async def test_get_fallback_rate_found(self, service, mock_db):
        mock_historical = MagicMock()
        mock_historical.rate = 3750.0
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_historical)))

        result = await service._get_fallback_rate("USD", "COP", mock_db)
        assert result["rate"] == 3750.0
        assert result["source"] == "ExchangeRate-Historical-Fallback"

    @pytest.mark.asyncio
    async def test_get_fallback_rate_not_found(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

        result = await service._get_fallback_rate("USD", "COP", mock_db)
        assert result is None

    # ─── get_exchange_rate ───

    @pytest.mark.asyncio
    async def test_get_exchange_rate_cached(self, service, mock_db):
        cached = {"rate": 3800.0, "source": "Cache"}
        with patch("app.services.exchange_rate_service.CacheService.get", AsyncMock(return_value=cached)):
            result = await service.get_exchange_rate("USD", "COP", mock_db)
            assert result["rate"] == 3800.0

    @pytest.mark.asyncio
    async def test_get_exchange_rate_no_api_key(self, service, mock_db):
        from app.core.exceptions import CustomException
        service.api_key = None
        with patch("app.services.exchange_rate_service.CacheService.get", AsyncMock(return_value=None)):
            with pytest.raises(CustomException, match="API Key"):
                await service.get_exchange_rate("USD", "COP", mock_db)

    @pytest.mark.asyncio
    async def test_get_exchange_rate_api_success(self, service, mock_db, mock_http):
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value={
            "result": "success",
            "conversion_rates": {"COP": 3800.0}
        })
        mock_http.get = AsyncMock(return_value=mock_response)
        service.http_client = mock_http

        with patch("app.services.exchange_rate_service.CacheService.get", AsyncMock(return_value=None)):
            with patch("app.services.exchange_rate_service.CacheService.set", AsyncMock()) as mock_set:
                result = await service.get_exchange_rate("USD", "COP", mock_db)
                assert result["rate"] == 3800.0
                mock_set.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_exchange_rate_all_attempts_fail_then_fallback(self, service, mock_db, mock_http):
        import httpx
        mock_http.get = AsyncMock(side_effect=httpx.HTTPError("API down"))
        service.http_client = mock_http

        mock_historical = MagicMock()
        mock_historical.rate = 3700.0
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_historical)))

        with patch("app.services.exchange_rate_service.CacheService.get", AsyncMock(return_value=None)):
            with patch("app.services.exchange_rate_service.CacheService.set", AsyncMock()):
                result = await service.get_exchange_rate("USD", "COP", mock_db)
                assert result["rate"] == 3700.0
                assert "Fallback" in result["source"]

    @pytest.mark.asyncio
    async def test_get_exchange_rate_all_fail_no_fallback(self, service, mock_db, mock_http):
        import httpx
        mock_http.get = AsyncMock(side_effect=httpx.HTTPError("API down"))
        service.http_client = mock_http

        mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

        from app.core.exceptions import CustomException
        with patch("app.services.exchange_rate_service.CacheService.get", AsyncMock(return_value=None)):
            with pytest.raises(CustomException, match="Error de conexión"):
                await service.get_exchange_rate("USD", "COP", mock_db)

    # ─── convert_currency ───

    @pytest.mark.asyncio
    async def test_convert_currency(self, service, mock_db):
        rate_data = {"rate": 3800.0, "timestamp": "now", "from_currency": "USD", "to_currency": "COP"}
        with patch.object(service, "get_exchange_rate", AsyncMock(return_value=rate_data)):
            result = await service.convert_currency(100.0, "USD", "COP", mock_db)
            assert result["converted_amount"] == 380000.0
            assert result["rate"] == 3800.0

    # ─── save_exchange_rate ───

    @pytest.mark.asyncio
    async def test_save_exchange_rate_new(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        await service.save_exchange_rate("USD", "COP", 3800.0, mock_db)
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_exchange_rate_update(self, service, mock_db):
        existing = MagicMock(rate=3700.0)
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing)))
        await service.save_exchange_rate("USD", "COP", 3800.0, mock_db)
        assert existing.rate == 3800.0
        mock_db.flush.assert_called_once()

    # ─── get_exchange_history ───

    @pytest.mark.asyncio
    async def test_get_exchange_history(self, service, mock_db):
        mock_rate = MagicMock()
        mock_rate.date = date.today()
        mock_rate.rate = 3800.0
        mock_db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_rate])))))

        result = await service.get_exchange_history("USD", "COP", 7, mock_db)
        assert len(result) == 1
        assert result[0]["rate"] == 3800.0

    @pytest.mark.asyncio
    async def test_get_exchange_history_empty(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))
        result = await service.get_exchange_history("USD", "COP", 7, mock_db)
        assert result == []

    # ─── get_multi_exchange_rates ───

    @pytest.mark.asyncio
    async def test_get_multi_exchange_rates_success(self, service, mock_db):
        rate_data = {"rate": 3800.0, "timestamp": "now"}
        with patch.object(service, "get_exchange_rate", AsyncMock(return_value=rate_data)):
            with patch.object(service, "save_exchange_rate", AsyncMock()):
                with patch.object(service, "get_exchange_history", AsyncMock(return_value=[])):
                    result = await service.get_multi_exchange_rates([("USD", "COP")], mock_db)
                    assert "USD_COP" in result
                    assert result["USD_COP"]["today"] == 3800.0

    @pytest.mark.asyncio
    async def test_get_multi_exchange_rates_error(self, service, mock_db):
        with patch.object(service, "get_exchange_rate", AsyncMock(side_effect=Exception("API error"))):
            result = await service.get_multi_exchange_rates([("USD", "COP")], mock_db)
            assert result == {}

    @pytest.mark.asyncio
    async def test_get_multi_exchange_rates_empty(self, service, mock_db):
        result = await service.get_multi_exchange_rates([], mock_db)
        assert result == {}

    # ─── preload_exchange_rates_task ───

    @pytest.mark.asyncio
    async def test_preload_task_success(self):
        from app.services.exchange_rate_service import preload_exchange_rates_task
        mock_session = AsyncMock()
        with patch("app.db.session.AsyncSessionLocal", MagicMock(return_value=mock_session)):
            with patch("app.services.exchange_rate_service.ExchangeRateService.__aenter__") as mock_enter:
                mock_service = AsyncMock()
                mock_service.get_exchange_rate = AsyncMock(return_value={"rate": 3800.0})
                mock_enter.return_value = mock_service
                result = await preload_exchange_rates_task()
                assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_preload_task_db_error(self):
        from app.services.exchange_rate_service import preload_exchange_rates_task
        with patch("app.db.session.AsyncSessionLocal", MagicMock(side_effect=Exception("DB error"))):
            result = await preload_exchange_rates_task()
            assert "error" in result
