from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limiter import limiter, stocks_rate_limit
from app.db.session import get_db
from app.services.alpha_vantage_service import AlphaVantageService
from app.services.exchange_rate_service import ExchangeRateService
from app.schemas.stock import StockInfo, HistoricalData

router = APIRouter()


@router.get(
    "/stocks/{symbol}",
    response_model=StockInfo,
    tags=["acciones"]
)
@limiter.limit(stocks_rate_limit)
async def get_stock(
    request: Request,
    symbol: str,
    db: AsyncSession = Depends(get_db)
):
    async with AlphaVantageService() as service:
        stock_data = await service.get_stock_price(symbol, db)
        return stock_data


@router.get(
    "/stocks/{symbol}/history",
    response_model=HistoricalData,
    tags=["acciones"]
)
@limiter.limit(stocks_rate_limit)
async def get_stock_history(
    request: Request,
    symbol: str,
    db: AsyncSession = Depends(get_db)
):
    async with AlphaVantageService() as service:
        historical_data = await service.get_historical_data(symbol, db)
        return historical_data


@router.get(
    "/exchange-rate",
    tags=["moneda"]
)
@limiter.limit(stocks_rate_limit)
async def get_exchange_rate(
    request: Request,
    from_currency: str = "USD",
    to_currency: str = "COP",
    db: AsyncSession = Depends(get_db)
):
    async with ExchangeRateService() as service:
        rate_data = await service.get_exchange_rate(from_currency, to_currency, db)
        return rate_data


@router.get(
    "/exchange-rate/convert",
    tags=["moneda"]
)
@limiter.limit(stocks_rate_limit)
async def convert_currency(
    request: Request,
    amount: float,
    from_currency: str = "USD",
    to_currency: str = "COP",
    db: AsyncSession = Depends(get_db)
):
    async with ExchangeRateService() as service:
        converted = await service.convert_currency(amount, from_currency, to_currency, db)
        return converted