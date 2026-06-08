from unittest.mock import AsyncMock, MagicMock, patch, ANY
from datetime import datetime

import pytest


class TestPDFReportService:
    def test_generate_portfolio_pdf_returns_bytes(self):
        from app.services.pdf_report_service import generate_portfolio_pdf
        user_data = {
            "username": "testuser",
            "initial_balance": 10000.0,
            "current_balance": 5000.0
        }
        portfolio = [
            {
                "symbol": "AAPL",
                "quantity": 10.0,
                "average_cost": 150.0,
                "current_price": 160.0,
                "stock_value": 1600.0,
                "stock_cost": 1500.0,
                "stock_profit": 100.0
            }
        ]
        result = generate_portfolio_pdf(user_data, portfolio, 3800.0)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_generate_portfolio_pdf_empty_portfolio(self):
        from app.services.pdf_report_service import generate_portfolio_pdf
        user_data = {"username": "testuser", "initial_balance": 10000.0, "current_balance": 10000.0}
        result = generate_portfolio_pdf(user_data, [], 3800.0)
        assert isinstance(result, bytes)

    def test_generate_portfolio_pdf_negative_profit(self):
        from app.services.pdf_report_service import generate_portfolio_pdf
        user_data = {"username": "testuser", "initial_balance": 10000.0, "current_balance": 8000.0}
        portfolio = [
            {
                "symbol": "TSLA",
                "quantity": 5.0,
                "average_cost": 200.0,
                "current_price": 150.0,
                "stock_value": 750.0,
                "stock_cost": 1000.0,
                "stock_profit": -250.0
            }
        ]
        result = generate_portfolio_pdf(user_data, portfolio, 3800.0)
        assert isinstance(result, bytes)

    def test_generate_portfolio_pdf_without_user_data(self):
        from app.services.pdf_report_service import generate_portfolio_pdf
        result = generate_portfolio_pdf({}, [], 0)
        assert isinstance(result, bytes)

    @pytest.mark.asyncio
    async def test_generate_report_user_not_found(self):
        from app.services.pdf_report_service import generate_report
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

        with pytest.raises(ValueError, match="User not found"):
            await generate_report(mock_db, 999)

    @pytest.mark.asyncio
    async def test_generate_report_empty_portfolio(self):
        from app.services.pdf_report_service import generate_report
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.username = "testuser"
        mock_user.initial_balance = 10000.0
        mock_user.current_balance = 5000.0

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_user),
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        ))

        with patch("app.services.pdf_report_service.generate_portfolio_pdf", MagicMock(return_value=b"%PDF-mock")):
            result = await generate_report(mock_db, 1)
            assert result == b"%PDF-mock"

    @pytest.mark.asyncio
    async def test_generate_report_with_portfolios(self):
        from app.services.pdf_report_service import generate_report
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.username = "testuser"
        mock_user.initial_balance = 10000.0
        mock_user.current_balance = 5000.0

        mock_portfolio = MagicMock()
        mock_portfolio.symbol = "AAPL"
        mock_portfolio.quantity = 10.0
        mock_portfolio.average_cost = 150.0

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_user),
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_portfolio])))
        ))

        mock_finnhub = AsyncMock()
        mock_finnhub.get_stock_price = AsyncMock(return_value={"price": 160.0})

        with patch("app.services.exchange_rate_service.ExchangeRateService.__aenter__") as mock_rate_enter:
            mock_rate_service = AsyncMock()
            mock_rate_service.get_exchange_rate = AsyncMock(return_value={"rate": 3800.0})
            mock_rate_enter.return_value = mock_rate_service

            with patch("app.services.finnhub_service.FinnhubService.__aenter__") as mock_enter:
                mock_enter.return_value = mock_finnhub
                with patch("app.services.pdf_report_service.generate_portfolio_pdf", MagicMock(return_value=b"%PDF-data")):
                    result = await generate_report(mock_db, 1)
                    assert result == b"%PDF-data"

    @pytest.mark.asyncio
    async def test_generate_report_price_fetch_error(self):
        from app.services.pdf_report_service import generate_report
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.username = "testuser"
        mock_user.initial_balance = 10000.0
        mock_user.current_balance = 5000.0

        mock_portfolio = MagicMock()
        mock_portfolio.symbol = "AAPL"
        mock_portfolio.quantity = 10.0
        mock_portfolio.average_cost = 150.0

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_user),
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[mock_portfolio])))
        ))

        with patch("app.services.finnhub_service.FinnhubService.__aenter__") as mock_enter:
            mock_finnhub = AsyncMock()
            mock_finnhub.get_stock_price = AsyncMock(return_value={"price": 0})
            mock_enter.return_value = mock_finnhub

            with patch("app.services.exchange_rate_service.ExchangeRateService.__aenter__") as mock_rate_enter:
                mock_rate = AsyncMock()
                mock_rate.get_exchange_rate = AsyncMock(side_effect=Exception("API error"))
                mock_rate_enter.return_value = mock_rate

                with patch("app.services.pdf_report_service.generate_portfolio_pdf", MagicMock(return_value=b"%PDF-error")):
                    result = await generate_report(mock_db, 1)
                    assert result == b"%PDF-error"

    def test_pdf_report_class_header_footer(self):
        from app.services.pdf_report_service import PDFReport
        pdf = PDFReport()
        pdf.add_page()
        pdf_bytes = pdf.output(dest='S').encode('latin-1')
        assert isinstance(pdf_bytes, bytes)
