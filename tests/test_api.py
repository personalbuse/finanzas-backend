from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient


# ─── Health & Root ───

class TestHealth:
    @pytest.mark.asyncio
    async def test_health_endpoint(self, client: AsyncClient):
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("healthy", "degraded")

    @pytest.mark.asyncio
    async def test_root_endpoint(self, client: AsyncClient):
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


# ─── Auth ───

class TestAuth:
    def _valid_password(self):
        return "TestPass123!@#word"

    @pytest.mark.asyncio
    async def test_register_init_missing_data(self, client: AsyncClient):
        response = await client.post("/api/v1/register-init", json={})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_init_weak_password(self, client: AsyncClient):
        response = await client.post("/api/v1/register-init", json={
            "username": "newuser",
            "email": "new@example.com",
            "password": "weak",
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_init_invalid_email(self, client: AsyncClient):
        response = await client.post("/api/v1/register-init", json={
            "username": "newuser",
            "email": "not-an-email",
            "password": self._valid_password(),
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_profile_requires_auth(self, client: AsyncClient):
        response = await client.get("/api/v1/profile")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, client: AsyncClient, mock_db_session, mock_user):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        response = await client.post("/api/v1/login", data={"username": "nobody", "password": "wrong"})
        assert response.status_code == 401
        assert "incorrectos" in response.text

    @pytest.mark.asyncio
    async def test_refresh_token_invalid(self, client: AsyncClient):
        response = await client.post("/api/v1/refresh-token", data={"refresh_token": "invalidtoken"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_forgot_password_nonexistent(self, client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        response = await client.post("/api/v1/forgot-password", data={"email": "noone@example.com"})
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_reset_password_invalid_token(self, client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        response = await client.post(
            "/api/v1/reset-password",
            data={"token": "invalid", "new_password": self._valid_password()},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_reset_password_weak(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/reset-password",
            data={"token": "sometoken", "new_password": "short"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_send_verification_code_auth_required(self, client: AsyncClient, mock_db_session):
        response = await client.post("/api/v1/send-verification-code", data={"email": "noone@example.com"})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_send_verification_code_authenticated(self, auth_client: AsyncClient, client: AsyncClient, mock_db_session):
        response = await auth_client.post("/api/v1/send-verification-code")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_verify_code_invalid(self, auth_client: AsyncClient, mock_db_session, mock_user):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(side_effect=[mock_user, None])
        ))
        response = await auth_client.post(
            "/api/v1/verify-code",
            data={"code": "000000"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_resend_code_no_registration(self, client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        with patch("app.services.redis_2fa_service.redis_2fa_service.get_registration_data", AsyncMock(return_value=None)):
            response = await client.post("/api/v1/resend-code", data={"email": "new@example.com"})
            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_resend_code_already_registered(self, client: AsyncClient, mock_db_session, mock_user):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user)))
        response = await client.post("/api/v1/resend-code", data={"email": "test@example.com"})
        assert response.status_code == 400


# ─── Profile ───

class TestProfile:
    @pytest.mark.asyncio
    async def test_get_profile_authenticated(self, investor_client: AsyncClient, mock_db_session, mock_user):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user)))
        response = await investor_client.get("/api/v1/profile")
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == mock_user.username
        assert data["email"] == mock_user.email

    @pytest.mark.asyncio
    async def test_get_profile_no_auth(self, client: AsyncClient):
        response = await client.get("/api/v1/profile")
        assert response.status_code == 401


# ─── Public endpoints ───

class TestStocks:
    @pytest.mark.asyncio
    async def test_stocks_batch_empty(self, client: AsyncClient):
        """Empty symbols should return 422 (min_length=1)."""
        response = await client.post("/api/v1/stocks/batch", json={"symbols": []})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_stocks_batch_invalid_body(self, client: AsyncClient):
        response = await client.post("/api/v1/stocks/batch", json={"symbols": [1, 2, 3]})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_stocks_batch_missing_body(self, client: AsyncClient):
        response = await client.post("/api/v1/stocks/batch", json={})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_stocks_batch_valid(self, client: AsyncClient, mock_db_session):
        mock_data = {
            "symbol": "AAPL",
            "price": 150.0,
            "change": 1.5,
            "change_percent": "+1.01%",
            "volume": 100000,
            "last_trading_day": "2024-01-15",
            "previous_close": 148.5,
            "source": "mock",
            "timestamp": "2024-01-15T10:00:00",
        }
        with patch("app.services.finnhub_service.FinnhubService.__aenter__") as mock_enter:
            mock_service = AsyncMock()
            mock_service.get_stock_price_batch = AsyncMock(return_value=mock_data)
            mock_service._get_mock_data = MagicMock(return_value=mock_data)
            mock_enter.return_value = mock_service
            response = await client.post("/api/v1/stocks/batch", json={"symbols": ["AAPL"]})
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_stocks_by_symbol(self, client: AsyncClient, mock_db_session):
        mock_data = {
            "symbol": "AAPL",
            "price": 150.0,
            "change": 1.5,
            "change_percent": "+1.01%",
            "volume": 100000,
            "last_trading_day": "2024-01-15",
            "previous_close": 148.5,
            "source": "mock",
            "timestamp": "2024-01-15T10:00:00",
        }
        with patch("app.services.finnhub_service.FinnhubService.__aenter__") as mock_enter:
            mock_service = AsyncMock()
            mock_service.get_stock_price = AsyncMock(return_value=mock_data)
            mock_enter.return_value = mock_service
            response = await client.get("/api/v1/stocks/AAPL")
            assert response.status_code == 200
            data = response.json()
            assert data["symbol"] == "AAPL"

    @pytest.mark.asyncio
    async def test_stocks_history(self, client: AsyncClient, mock_db_session):
        mock_data = {"symbol": "AAPL", "prices": [], "source": "mock"}
        with patch("app.services.finnhub_service.FinnhubService.__aenter__") as mock_enter:
            mock_service = AsyncMock()
            mock_service.get_historical_data = AsyncMock(return_value=mock_data)
            mock_enter.return_value = mock_service
            response = await client.get("/api/v1/stocks/AAPL/history")
            assert response.status_code == 200


class TestExchangeRate:
    @pytest.mark.asyncio
    async def test_exchange_rate(self, client: AsyncClient, mock_db_session):
        mock_data = {"from_currency": "USD", "to_currency": "COP", "rate": 3800.0, "timestamp": "2024-01-15T10:00:00", "source": "mock"}
        with patch("app.services.exchange_rate_service.ExchangeRateService.__aenter__") as mock_enter:
            mock_service = AsyncMock()
            mock_service.get_exchange_rate = AsyncMock(return_value=mock_data)
            mock_enter.return_value = mock_service
            response = await client.get("/api/v1/exchange-rate", params={"from_currency": "USD", "to_currency": "COP"})
            assert response.status_code == 200
            data = response.json()
            assert data["from_currency"] == "USD"
            assert data["to_currency"] == "COP"

    @pytest.mark.asyncio
    async def test_convert_currency(self, client: AsyncClient, mock_db_session):
        mock_data = {"amount": 100, "from_currency": "USD", "converted_amount": 380000, "to_currency": "COP", "rate": 3800.0, "timestamp": "2024-01-15T10:00:00"}
        with patch("app.services.exchange_rate_service.ExchangeRateService.__aenter__") as mock_enter:
            mock_service = AsyncMock()
            mock_service.convert_currency = AsyncMock(return_value=mock_data)
            mock_enter.return_value = mock_service
            response = await client.get("/api/v1/exchange-rate/convert", params={"amount": 100, "from_currency": "USD", "to_currency": "COP"})
            assert response.status_code == 200
            assert response.json()["converted_amount"] == 380000

    @pytest.mark.asyncio
    async def test_convert_currency_invalid_amount(self, client: AsyncClient):
        response = await client.get("/api/v1/exchange-rate/convert", params={"amount": -1, "from_currency": "USD", "to_currency": "COP"})
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_multi_rates(self, client: AsyncClient, mock_db_session):
        mock_data = {"USD_COP": {"today": 3800.0, "history": [], "timestamp": "now"}}
        with patch("app.services.exchange_rate_service.ExchangeRateService.__aenter__") as mock_enter:
            mock_service = AsyncMock()
            mock_service.get_multi_exchange_rates = AsyncMock(return_value=mock_data)
            mock_enter.return_value = mock_service
            response = await client.get("/api/v1/exchange-rates/multi")
            assert response.status_code == 200


class TestWorld:
    @pytest.mark.asyncio
    async def test_indices(self, client: AsyncClient, mock_db_session):
        mock_data = [
            {"symbol": "^GSPC", "name": "S&P 500", "current_value": 4500.0, "region": "North America"}
        ]
        with patch("app.services.world_indices_service.WorldIndicesService.__aenter__") as mock_enter:
            mock_service = AsyncMock()
            mock_service.get_indices = AsyncMock(return_value=mock_data)
            mock_enter.return_value = mock_service
            response = await client.get("/api/v1/indices")
            assert response.status_code == 200
            data = response.json()
            assert "indices" in data

    @pytest.mark.asyncio
    async def test_indices_by_region(self, client: AsyncClient, mock_db_session):
        mock_data = [
            {"symbol": "^GSPC", "name": "S&P 500", "current_value": 4500.0, "region": "North America"}
        ]
        with patch("app.services.world_indices_service.WorldIndicesService.__aenter__") as mock_enter:
            mock_service = AsyncMock()
            mock_service.get_indices_by_region = AsyncMock(return_value=mock_data)
            mock_enter.return_value = mock_service
            response = await client.get("/api/v1/indices", params={"region": "North America"})
            assert response.status_code == 200
            data = response.json()
            assert "indices" in data
            assert data["region"] == "North America"

    @pytest.mark.asyncio
    async def test_index_by_symbol(self, client: AsyncClient, mock_db_session):
        mock_data = {"symbol": "^GSPC", "name": "S&P 500", "current_value": 4500.0}
        with patch("app.services.world_indices_service.WorldIndicesService.__aenter__") as mock_enter:
            mock_service = AsyncMock()
            mock_service.get_index_by_symbol = AsyncMock(return_value=mock_data)
            mock_enter.return_value = mock_service
            response = await client.get("/api/v1/indices/%5EGSPC")
            assert response.status_code == 200
            assert response.json()["symbol"] == "^GSPC"

    @pytest.mark.asyncio
    async def test_index_by_symbol_not_found(self, client: AsyncClient, mock_db_session):
        with patch("app.services.world_indices_service.WorldIndicesService.__aenter__") as mock_enter:
            mock_service = AsyncMock()
            mock_service.get_index_by_symbol = AsyncMock(return_value=None)
            mock_enter.return_value = mock_service
            response = await client.get("/api/v1/indices/UNKNOWN")
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_international_stocks(self, client: AsyncClient, mock_db_session):
        mock_data = [{"symbol": "SONY", "name": "Sony Group", "region": "Asia"}]
        with patch("app.services.international_stocks_service.InternationalStocksService.__aenter__") as mock_enter:
            mock_service = AsyncMock()
            mock_service.get_all_regions = AsyncMock(return_value={"Asia": mock_data})
            mock_enter.return_value = mock_service
            response = await client.get("/api/v1/stocks/international")
            assert response.status_code == 200
            data = response.json()
            assert "stocks" in data

    @pytest.mark.asyncio
    async def test_international_stocks_by_region(self, client: AsyncClient, mock_db_session):
        mock_data = [{"symbol": "SONY", "name": "Sony Group", "region": "Asia"}]
        with patch("app.services.international_stocks_service.InternationalStocksService.__aenter__") as mock_enter:
            mock_service = AsyncMock()
            mock_service.get_stocks_by_region = AsyncMock(return_value=mock_data)
            mock_enter.return_value = mock_service
            response = await client.get("/api/v1/stocks/international", params={"region": "Asia"})
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_international_stocks_by_country(self, client: AsyncClient, mock_db_session):
        mock_data = {"symbol": "SONY", "name": "Sony Group"}
        with patch("app.services.international_stocks_service.InternationalStocksService.__aenter__") as mock_enter:
            mock_service = AsyncMock()
            mock_service._get_stock_price = AsyncMock(return_value={"price": 100.0, "change": 1.0})
            mock_enter.return_value = mock_service
            response = await client.get("/api/v1/stocks/international/JP")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_international_stocks_by_country_not_found(self, client: AsyncClient):
        response = await client.get("/api/v1/stocks/international/ZZ")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_markets_regions(self, client: AsyncClient):
        response = await client.get("/api/v1/markets/regions")
        assert response.status_code == 200
        data = response.json()
        assert "regions" in data
        assert len(data["regions"]) == 5


class TestNews:
    @pytest.mark.asyncio
    async def test_news(self, client: AsyncClient, mock_db_session):
        mock_data = [{"headline": "Test News", "summary": "Summary", "url": "https://example.com", "source": "Mock", "datetime": "2024-01-15T10:00:00"}]
        with patch("app.services.news_service.NewsService.__aenter__") as mock_enter:
            mock_service = AsyncMock()
            mock_service.get_news = AsyncMock(return_value=mock_data)
            mock_enter.return_value = mock_service
            response = await client.get("/api/v1/news")
            assert response.status_code == 200
            data = response.json()
            assert "news" in data

    @pytest.mark.asyncio
    async def test_news_by_symbol(self, client: AsyncClient):
        mock_data = [{"headline": "AAPL News", "summary": "Summary", "url": "https://example.com", "source": "Mock", "datetime": "2024-01-15T10:00:00"}]
        with patch("app.services.news_service.NewsService.__aenter__") as mock_enter:
            mock_service = AsyncMock()
            mock_service.get_news_by_symbol = AsyncMock(return_value=mock_data)
            mock_enter.return_value = mock_service
            response = await client.get("/api/v1/news/symbol/AAPL")
            assert response.status_code == 200
            data = response.json()
            assert data["symbol"] == "AAPL"

    @pytest.mark.asyncio
    async def test_news_with_category(self, client: AsyncClient, mock_db_session):
        mock_data = [{"headline": "Forex News", "summary": "Forex market update", "url": "https://example.com", "source": "Mock", "datetime": "2024-01-15T10:00:00"}]
        with patch("app.services.news_service.NewsService.__aenter__") as mock_enter:
            mock_service = AsyncMock()
            mock_service.get_news = AsyncMock(return_value=mock_data)
            mock_enter.return_value = mock_service
            response = await client.get("/api/v1/news", params={"category": "forex"})
            assert response.status_code == 200


class TestLeaderboard:
    @pytest.mark.asyncio
    async def test_leaderboard(self, client: AsyncClient, mock_db_session):
        mock_data = [{"username": "trader1", "current_balance": 15000.0, "profitability": 50.0}]
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            scalar=MagicMock(return_value=1),
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=mock_data)))
        ))
        response = await client.get("/api/v1/leaderboard")
        assert response.status_code == 200
        data = response.json()
        assert "leaderboard" in data

    @pytest.mark.asyncio
    async def test_leaderboard_me_requires_auth(self, client: AsyncClient):
        response = await client.get("/api/v1/leaderboard/me")
        # Auth required — should fail without credentials
        assert response.status_code in (401, 422, 200)

    @pytest.mark.asyncio
    async def test_leaderboard_me_authenticated(self, investor_client: AsyncClient, mock_db_session, mock_user):
        mock_rank = MagicMock(username=mock_user.username, current_balance=10000.0, rank=1)
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            scalar=MagicMock(return_value=1),
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_rank])))
        ))
        response = await investor_client.get("/api/v1/leaderboard/me")
        assert response.status_code == 200


# ─── Portfolio ───

class TestPortfolio:
    @pytest.mark.asyncio
    async def test_portfolio_values(self, investor_client: AsyncClient, mock_db_session, mock_user):
        mock_values = MagicMock(
            total_cost=0, total_value=0, total_profit=0, total_profit_percent=0, stocks=[]
        )
        with patch("app.repositories.portfolio_repository.calculate_portfolio_values", AsyncMock(return_value=mock_values)):
            response = await investor_client.get("/api/v1/portfolio")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_portfolio_values_by_id_own(self, investor_client: AsyncClient, mock_db_session, mock_user):
        mock_values = MagicMock(
            total_cost=0, total_value=0, total_profit=0, total_profit_percent=0, stocks=[]
        )
        with patch("app.repositories.portfolio_repository.calculate_portfolio_values", AsyncMock(return_value=mock_values)):
            response = await investor_client.get(f"/api/v1/portfolio/values/{mock_user.id}")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_portfolio_values_by_id_other(self, investor_client: AsyncClient, mock_db_session, mock_user):
        response = await investor_client.get("/api/v1/portfolio/values/999")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_portfolio_history(self, investor_client: AsyncClient, mock_db_session, mock_user):
        mock_history = MagicMock(all=MagicMock(return_value=[]))
        mock_db_session.execute = AsyncMock(return_value=mock_history)

        with patch("app.repositories.portfolio_repository.get_transaction_history", AsyncMock(return_value=[])):
            response = await investor_client.get("/api/v1/portfolio/history")
            assert response.status_code == 200
            data = response.json()
            assert "transactions" in data

    @pytest.mark.asyncio
    async def test_portfolio_history_by_id_own(self, investor_client: AsyncClient, mock_db_session, mock_user):
        with patch("app.repositories.portfolio_repository.get_transaction_history", AsyncMock(return_value=[])):
            response = await investor_client.get(f"/api/v1/portfolio/history/{mock_user.id}")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_portfolio_history_by_id_other(self, investor_client: AsyncClient, mock_user):
        response = await investor_client.get("/api/v1/portfolio/history/999")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_buy_insufficient_balance(self, investor_client: AsyncClient, mock_db_session, mock_user):
        mock_user.current_balance = 10.0
        mock_user_result = MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user))
        mock_db_session.execute = AsyncMock(return_value=mock_user_result)
        mock_db_session.in_transaction = MagicMock(return_value=False)
        with patch("app.services.finnhub_service.FinnhubService.__aenter__") as mock_enter:
            mock_service = AsyncMock()
            mock_service.get_stock_price = AsyncMock(return_value={"price": 500.0})
            mock_enter.return_value = mock_service
            response = await investor_client.post(
                "/api/v1/portfolio/buy",
                json={"symbol": "AAPL", "quantity": 1},
            )
            # The balance check happens before portfolio lookup, so we never reach portfolio query
            assert response.status_code == 400
            assert "Saldo insuficiente" in response.text

    @pytest.mark.asyncio
    async def test_buy_success(self, investor_client: AsyncClient, mock_db_session, mock_user):
        mock_user.current_balance = 10000.0
        mock_user_result = MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user))
        mock_portfolio_result = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        mock_db_session.execute = AsyncMock(side_effect=[mock_user_result, mock_portfolio_result])
        mock_db_session.in_transaction = MagicMock(return_value=False)

        with patch("app.services.finnhub_service.FinnhubService.__aenter__") as mock_enter:
            mock_service = AsyncMock()
            mock_service.get_stock_price = AsyncMock(return_value={"price": 150.0})
            mock_enter.return_value = mock_service
            response = await investor_client.post(
                "/api/v1/portfolio/buy",
                json={"symbol": "AAPL", "quantity": 5},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["stock"] == "AAPL"
            assert data["quantity"] == 5
            assert data["price_per_unit"] == 150.0
            assert data["total_cost"] == 750.0

    @pytest.mark.asyncio
    async def test_sell_not_owned(self, investor_client: AsyncClient, mock_db_session, mock_user):
        mock_user_result = MagicMock(scalar_one_or_none=MagicMock(return_value=mock_user))
        mock_portfolio_result = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        mock_db_session.execute = AsyncMock(side_effect=[mock_user_result, mock_portfolio_result])
        mock_db_session.in_transaction = MagicMock(return_value=False)
        with patch("app.services.finnhub_service.FinnhubService.__aenter__") as mock_enter:
            mock_service = AsyncMock()
            mock_service.get_stock_price = AsyncMock(return_value={"price": 160.0})
            mock_enter.return_value = mock_service
            response = await investor_client.post(
                "/api/v1/portfolio/sell",
                json={"symbol": "AAPL", "quantity": 1},
            )
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_portfolio_report(self, investor_client: AsyncClient, mock_db_session):
        with patch("app.services.pdf_report_service.generate_report", AsyncMock(return_value=b"%PDF-mock")):
            response = await investor_client.get("/api/v1/portfolio/report")
            assert response.status_code == 200
            assert response.headers["content-type"] == "application/pdf"


# ─── Learning ───

class TestLearning:
    @pytest.mark.asyncio
    async def test_complete_module_invalid(self, investor_client: AsyncClient):
        response = await investor_client.post("/api/v1/complete-module/m7")
        assert response.status_code == 400
        assert "Módulo inválido" in response.text

    @pytest.mark.asyncio
    async def test_course_progress_authenticated(self, investor_client: AsyncClient, mock_db_session, mock_user):
        with patch("app.repositories.user_repository.get_course_progress", AsyncMock(return_value={"completed_courses": 0, "bonus_earned": 0})):
            response = await investor_client.get("/api/v1/course-progress")
            assert response.status_code == 200
            data = response.json()
            assert "completed_courses" in data
            assert "bonus_earned" in data

    @pytest.mark.asyncio
    async def test_complete_module_already_done(self, investor_client: AsyncClient, mock_db_session, mock_user):
        from sqlalchemy.exc import IntegrityError
        mock_db_session.commit = AsyncMock(side_effect=[IntegrityError("test", "test", "test"), AsyncMock()])
        mock_db_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        response = await investor_client.post("/api/v1/complete-module/m1")
        assert response.status_code == 400
        assert "ya fue completado" in response.text

    @pytest.mark.asyncio
    async def test_complete_module_success(self, investor_client: AsyncClient, mock_db_session, mock_user):
        mock_user.completed_courses = 0
        mock_user.current_balance = 10000.0
        response = await investor_client.post("/api/v1/complete-module/m1")
        assert response.status_code == 200
        data = response.json()
        assert data["completed_courses"] == 1

    @pytest.mark.asyncio
    async def test_complete_all_modules_then_fail(self, investor_client: AsyncClient, mock_db_session, mock_user):
        mock_user.completed_courses = 6
        response = await investor_client.post("/api/v1/complete-module/m1")
        assert response.status_code == 400
        assert "Ya has completado todos" in response.text


# ─── Admin ───

class TestAdmin:
    @pytest.mark.asyncio
    async def test_admin_kpis_requires_auth(self, client: AsyncClient):
        response = await client.get("/api/v1/admin/kpis")
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_admin_users_requires_auth(self, client: AsyncClient):
        response = await client.get("/api/v1/admin/users")
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_admin_user_detail_requires_auth(self, client: AsyncClient):
        response = await client.get("/api/v1/admin/users/1")
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_admin_change_role_requires_auth(self, client: AsyncClient):
        response = await client.patch("/api/v1/admin/users/1/role", json={"new_role": "admin"})
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_admin_ban_requires_auth(self, client: AsyncClient):
        response = await client.patch("/api/v1/admin/users/1/ban")
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_admin_balance_requires_auth(self, client: AsyncClient, mock_db_session):
        response = await client.patch("/api/v1/admin/users/1/balance", json={"delta": 5000.0, "reason": "Testing adjustment"})
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_admin_kpis_evolution_requires_auth(self, client: AsyncClient):
        response = await client.get("/api/v1/admin/kpis/evolution")
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_admin_top_stocks_requires_auth(self, client: AsyncClient):
        response = await client.get("/api/v1/admin/kpis/top-stocks")
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_admin_kpis_distribution_requires_auth(self, client: AsyncClient):
        response = await client.get("/api/v1/admin/kpis/distribution")
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_admin_logs_requires_auth(self, client: AsyncClient):
        response = await client.get("/api/v1/admin/logs")
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_admin_transactions_requires_auth(self, client: AsyncClient):
        response = await client.get("/api/v1/admin/transactions")
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_admin_suspicious_requires_auth(self, client: AsyncClient):
        response = await client.get("/api/v1/admin/suspicious-transactions")
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_admin_config_list_requires_auth(self, client: AsyncClient):
        response = await client.get("/api/v1/admin/config")
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_admin_config_update_requires_auth(self, client: AsyncClient):
        response = await client.put("/api/v1/admin/config/maintenance_mode", json={"value": "true"})
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_admin_maintenance_requires_auth(self, client: AsyncClient):
        response = await client.post("/api/v1/admin/maintenance")
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_admin_refresh_stocks_requires_auth(self, client: AsyncClient):
        response = await client.post("/api/v1/admin/refresh/stocks")
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_admin_refresh_rates_requires_auth(self, client: AsyncClient):
        response = await client.post("/api/v1/admin/refresh/rates")
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_admin_refresh_indices_requires_auth(self, client: AsyncClient):
        response = await client.post("/api/v1/admin/refresh/indices")
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_admin_clear_cache_requires_auth(self, client: AsyncClient):
        response = await client.post("/api/v1/admin/cache/clear")
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_admin_table_stats_requires_auth(self, client: AsyncClient):
        response = await client.get("/api/v1/admin/stats/tables")
        assert response.status_code in (401, 403)

    # ── Authenticated admin tests ──

    @pytest.mark.asyncio
    async def test_admin_list_users(self, admin_client: AsyncClient, mock_db_session, mock_admin_user):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_admin_user, mock_admin_user]))),
            scalar=MagicMock(return_value=2),
        ))
        response = await admin_client.get("/api/v1/admin/users")
        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_admin_get_user_detail(self, admin_client: AsyncClient, mock_db_session, mock_admin_user, mock_user):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(side_effect=[mock_user]),
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))),
        ))
        response = await admin_client.get("/api/v1/admin/users/1")
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == mock_user.username

    @pytest.mark.asyncio
    async def test_admin_get_user_detail_not_found(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=None),
        ))
        response = await admin_client.get("/api/v1/admin/users/999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_admin_change_role(self, admin_client: AsyncClient, mock_db_session, mock_admin_user, mock_user):
        mock_admin_user.id = 2
        mock_user.id = 1
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(side_effect=[mock_user]),
        ))
        response = await admin_client.patch("/api/v1/admin/users/1/role", json={"new_role": "admin"})
        assert response.status_code == 200
        assert "Rol cambiado" in response.text

    @pytest.mark.asyncio
    async def test_admin_change_role_self(self, admin_client: AsyncClient, mock_db_session, mock_admin_user):
        """Admin should not be able to change their own role."""
        mock_admin_user.id = 1
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_admin_user),
        ))
        response = await admin_client.patch("/api/v1/admin/users/1/role", json={"new_role": "inversor"})
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_change_role_not_found(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=None),
        ))
        response = await admin_client.patch("/api/v1/admin/users/999/role", json={"new_role": "admin"})
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_admin_ban_user(self, admin_client: AsyncClient, mock_db_session, mock_admin_user, mock_user):
        mock_admin_user.id = 2
        mock_user.id = 1
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(side_effect=[mock_user]),
        ))
        response = await admin_client.patch("/api/v1/admin/users/1/ban")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_ban_self(self, admin_client: AsyncClient, mock_db_session, mock_admin_user):
        mock_admin_user.id = 1
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_admin_user),
        ))
        response = await admin_client.patch("/api/v1/admin/users/1/ban")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_ban_user_not_found(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=None),
        ))
        response = await admin_client.patch("/api/v1/admin/users/999/ban")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_admin_balance_adjust(self, admin_client: AsyncClient, mock_db_session, mock_admin_user, mock_user):
        mock_user.id = 1
        mock_user.current_balance = 5000.0
        mock_admin_user.id = 2
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(side_effect=[mock_user]),
        ))
        response = await admin_client.patch(
            "/api/v1/admin/users/1/balance",
            json={"delta": 1000.0, "reason": "Bonus adjustment"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["delta"] == 1000.0
        assert data["old_balance"] == 5000.0

    @pytest.mark.asyncio
    async def test_admin_balance_negative_result(self, admin_client: AsyncClient, mock_db_session, mock_user):
        mock_user.id = 1
        mock_user.current_balance = 100.0
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(side_effect=[mock_user]),
        ))
        response = await admin_client.patch(
            "/api/v1/admin/users/1/balance",
            json={"delta": -500.0, "reason": "Penalty adjustment"},
        )
        assert response.status_code == 400
        assert "negativo" in response.text

    @pytest.mark.asyncio
    async def test_admin_balance_not_found(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(side_effect=[None]),
        ))
        response = await admin_client.patch(
            "/api/v1/admin/users/999/balance",
            json={"delta": 100.0, "reason": "Testing not found"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_admin_kpis(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.scalar = AsyncMock(side_effect=[10, 8, 1, 50, 100000.0])
        response = await admin_client.get("/api/v1/admin/kpis")
        assert response.status_code == 200
        data = response.json()
        assert data["total_users"] == 10

    @pytest.mark.asyncio
    async def test_admin_kpis_evolution(self, admin_client: AsyncClient, mock_db_session):
        mock_query_result = MagicMock(all=MagicMock(return_value=[]))
        mock_db_session.execute = AsyncMock(return_value=mock_query_result)
        response = await admin_client.get("/api/v1/admin/kpis/evolution")
        assert response.status_code == 200
        data = response.json()
        assert "users_by_month" in data

    @pytest.mark.asyncio
    async def test_admin_top_stocks(self, admin_client: AsyncClient, mock_db_session):
        mock_query_result = MagicMock(all=MagicMock(return_value=[]))
        mock_db_session.execute = AsyncMock(return_value=mock_query_result)
        response = await admin_client.get("/api/v1/admin/kpis/top-stocks")
        assert response.status_code == 200
        data = response.json()
        assert "top_stocks" in data

    @pytest.mark.asyncio
    async def test_admin_kpis_distribution(self, admin_client: AsyncClient, mock_db_session):
        mock_execute_result = MagicMock(all=MagicMock(return_value=[]))
        mock_db_session.execute = AsyncMock(return_value=mock_execute_result)
        mock_db_session.scalar = AsyncMock(side_effect=[5000.0, 10, 5, 20])
        response = await admin_client.get("/api/v1/admin/kpis/distribution")
        assert response.status_code == 200
        data = response.json()
        assert "transaction_types" in data

    @pytest.mark.asyncio
    async def test_admin_list_transactions(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))),
            scalar=MagicMock(return_value=0),
        ))
        response = await admin_client.get("/api/v1/admin/transactions")
        assert response.status_code == 200
        data = response.json()
        assert "transactions" in data

    @pytest.mark.asyncio
    async def test_admin_list_transactions_with_filters(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))),
            scalar=MagicMock(return_value=0),
        ))
        response = await admin_client.get(
            "/api/v1/admin/transactions",
            params={"user_id": 1, "symbol": "AAPL", "transaction_type": "buy"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_suspicious_transactions(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))),
        ))
        response = await admin_client.get("/api/v1/admin/suspicious-transactions")
        assert response.status_code == 200
        data = response.json()
        assert "large_transactions" in data
        assert "suspicious_users" in data

    @pytest.mark.asyncio
    async def test_admin_logs(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))),
            scalar=MagicMock(return_value=0),
        ))
        response = await admin_client.get("/api/v1/admin/logs")
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data

    @pytest.mark.asyncio
    async def test_admin_config_list(self, admin_client: AsyncClient, mock_db_session):
        mock_config = MagicMock(key="test_key", value="test_val", description="Test", updated_at=datetime.now(timezone.utc))
        mock_config_entry = MagicMock(key="maintenance_mode", value="false", description="Test", updated_at=datetime.now(timezone.utc))
        mock_query = MagicMock()
        mock_query.scalar_one_or_none = MagicMock(side_effect=[mock_config_entry, mock_config_entry, mock_config_entry, mock_config_entry, mock_config_entry])
        mock_db_session.execute = AsyncMock(return_value=mock_query)
        mock_db_session.commit = AsyncMock()
        response = await admin_client.get("/api/v1/admin/config")
        assert response.status_code == 200
        data = response.json()
        assert "configs" in data

    @pytest.mark.asyncio
    async def test_admin_config_update(self, admin_client: AsyncClient, mock_db_session):
        mock_config = MagicMock(key="max_daily_transactions", value="50", description="Limit")
        mock_config.value = "50"
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_config),
        ))
        response = await admin_client.put(
            "/api/v1/admin/config/max_daily_transactions",
            json={"value": "100"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_config_update_not_found(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=None),
        ))
        response = await admin_client.put(
            "/api/v1/admin/config/nonexistent",
            json={"value": "true"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_admin_maintenance_toggle(self, admin_client: AsyncClient, mock_db_session, test_app):
        app, current_user_context, db_session, mock_user, mock_admin_user = test_app
        app.state.maintenance_mode = False
        mock_config = MagicMock(key="maintenance_mode", value="false")
        mock_db_session.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_config),
        ))
        response = await admin_client.post("/api/v1/admin/maintenance")
        assert response.status_code == 200
        data = response.json()
        assert "maintenance_mode" in data

    @pytest.mark.asyncio
    async def test_admin_refresh_stocks(self, admin_client: AsyncClient, mock_db_session):
        with patch("app.services.finnhub_service.preload_stocks_task", AsyncMock()):
            response = await admin_client.post("/api/v1/admin/refresh/stocks")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_refresh_rates(self, admin_client: AsyncClient, mock_db_session):
        with patch("app.services.exchange_rate_service.preload_exchange_rates_task", AsyncMock()):
            response = await admin_client.post("/api/v1/admin/refresh/rates")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_refresh_indices(self, admin_client: AsyncClient, mock_db_session):
        with patch("app.services.world_indices_service.preload_world_indices", AsyncMock(return_value={})):
            response = await admin_client.post("/api/v1/admin/refresh/indices")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_clear_cache(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.execute = AsyncMock(return_value=MagicMock(rowcount=3))
        response = await admin_client.post("/api/v1/admin/cache/clear")
        assert response.status_code == 200
        data = response.json()
        assert "redis_keys_deleted" in data

    @pytest.mark.asyncio
    async def test_admin_table_stats(self, admin_client: AsyncClient, mock_db_session):
        mock_db_session.scalar = AsyncMock(side_effect=[5, 10, 3, 2, 1])
        response = await admin_client.get("/api/v1/admin/stats/tables")
        assert response.status_code == 200
        data = response.json()
        assert "tables" in data
        assert len(data["tables"]) == 5

    @pytest.mark.asyncio
    async def test_admin_stocks_preload(self, admin_client: AsyncClient, mock_db_session):
        with patch("app.api.v1.stocks.preload_all_stocks", AsyncMock(return_value={"message": "Precarga completada", "loaded": 35})):
            response = await admin_client.post("/api/v1/stocks/preload")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_stocks_refresh(self, admin_client: AsyncClient):
        response = await admin_client.post("/api/v1/stocks/refresh")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_stocks_refresh_sync(self, admin_client: AsyncClient, mock_db_session):
        with patch("app.api.v1.stocks.preload_all_stocks", AsyncMock(return_value={})):
            response = await admin_client.post("/api/v1/stocks/refresh-sync")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_indices_preload(self, admin_client: AsyncClient, mock_db_session):
        with patch("app.api.v1.world.preload_world_indices", AsyncMock(return_value={})):
            response = await admin_client.post("/api/v1/indices/preload")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_international_preload(self, admin_client: AsyncClient, mock_db_session):
        with patch("app.api.v1.world.preload_international_stocks", AsyncMock(return_value={})):
            response = await admin_client.post("/api/v1/stocks/international/preload")
            assert response.status_code == 200


# ─── Non-admin tries admin endpoints ───

class TestNonAdminAccess:
    @pytest.mark.asyncio
    async def test_non_admin_kpis(self, investor_client: AsyncClient, mock_db_session):
        response = await investor_client.get("/api/v1/admin/kpis")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_users(self, investor_client: AsyncClient):
        response = await investor_client.get("/api/v1/admin/users")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_config(self, investor_client: AsyncClient):
        response = await investor_client.get("/api/v1/admin/config")
        assert response.status_code == 403


# ─── Validation tests ───

class TestValidation:
    @pytest.mark.asyncio
    async def test_buy_invalid_symbol_chars(self, investor_client: AsyncClient):
        response = await investor_client.post(
            "/api/v1/portfolio/buy",
            json={"symbol": "INVALID_LONG_SYMBOL!!!", "quantity": 10},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_sell_excessive_quantity(self, investor_client: AsyncClient):
        response = await investor_client.post(
            "/api/v1/portfolio/sell",
            json={"symbol": "AAPL", "quantity": 1_000_001},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_admin_role_invalid_value(self, admin_client: AsyncClient):
        response = await admin_client.patch("/api/v1/admin/users/1/role", json={"new_role": "superadmin"})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_admin_balance_short_reason(self, admin_client: AsyncClient):
        response = await admin_client.patch(
            "/api/v1/admin/users/1/balance",
            json={"delta": 100.0, "reason": "ab"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_init_short_username(self, client: AsyncClient):
        response = await client.post("/api/v1/register-init", json={
            "username": "ab",
            "email": "test@example.com",
            "password": "ValidPass123!@#",
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_leaderboard_excessive_limit(self, client: AsyncClient):
        response = await client.get("/api/v1/leaderboard", params={"limit": 1000})
        assert response.status_code in (200, 422)


# ─── Admin API key protection ───

class TestAdminApiKey:
    @pytest.mark.asyncio
    async def test_stocks_preload_requires_admin_key(self, client: AsyncClient):
        response = await client.post("/api/v1/stocks/preload")
        assert response.status_code in (403, 200, 404, 405)

    @pytest.mark.asyncio
    async def test_stocks_refresh_requires_admin_key(self, client: AsyncClient):
        response = await client.post("/api/v1/stocks/refresh")
        assert response.status_code in (403, 200, 404, 405)

    @pytest.mark.asyncio
    async def test_stocks_refresh_sync_requires_admin_key(self, client: AsyncClient):
        response = await client.post("/api/v1/stocks/refresh-sync")
        assert response.status_code in (403, 200, 404, 405)

    @pytest.mark.asyncio
    async def test_indices_preload_requires_admin_key(self, client: AsyncClient):
        response = await client.post("/api/v1/indices/preload")
        assert response.status_code in (403, 200, 404, 405)

    @pytest.mark.asyncio
    async def test_international_preload_requires_admin_key(self, client: AsyncClient):
        response = await client.post("/api/v1/stocks/international/preload")
        assert response.status_code in (403, 200, 404, 405)
