from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from pydantic import BaseModel
import logging

from app.core.rate_limiter import limiter, stocks_rate_limit
from app.db.session import get_db
from app.services.alpha_vantage_service import AlphaVantageService
from app.services.exchange_rate_service import ExchangeRateService
from app.schemas.stock import StockInfo, HistoricalData

router = APIRouter()
logger = logging.getLogger(__name__)

# Lista de 35 stocks principales para precargar
PRELOAD_STOCKS = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'NFLX', 'AMD', 'INTC',
    'BA', 'JNJ', 'UNH', 'HD', 'PG', 'MA', 'DIS', 'V', 'KO', 'PEP',
    'CSCO', 'T', 'ADBE', 'CRM', 'CMCSA', 'XOM', 'PFE', 'ORCL', 'QCOM', 'TXN',
    'AVGO', 'COST', 'MCD', 'NKE', 'WMT'
]


@router.post("/stocks/preload", tags=["admin"])
async def preload_stocks(db: AsyncSession = Depends(get_db)):
    """Endpoint para precargar todos los stocks en cache.
    
    Uso: docker exec <container> curl http://localhost:8000/api/v1/stocks/preload
    Configurar en cron: 1 0 * * * docker exec <container> curl http://localhost:8000/api/v1/stocks/preload
    """
    logger.info(f"Iniciando precarga de {len(PRELOAD_STOCKS)} stocks (esto tardara ~7 minutos)...")
    
    loaded_count = 0
    failed_count = 0
    
    async with AlphaVantageService() as service:
        for i, symbol in enumerate(PRELOAD_STOCKS):
            try:
                await service.get_stock_price(symbol, db, 86400)  # 24h cache
                loaded_count += 1
                logger.info(f"Stock {i+1}/{len(PRELOAD_STOCKS)} cargado: {symbol}")
                
                # Agregar delay para evitar rate limit (5/min) - ejecutar 35 stocks = 7 min
                if i < len(PRELOAD_STOCKS) - 1:
                    import asyncio
                    await asyncio.sleep(12)  # 12 segundos entre cada llamada
                    
            except Exception as e:
                failed_count += 1
                logger.error(f"Error cargando {symbol}: {e}")
    
    logger.info(f"Precarga completada: {loaded_count} exitosos, {failed_count} fallidos")
    
    return {
        "total": len(PRELOAD_STOCKS),
        "loaded": loaded_count,
        "failed": failed_count
    }


class BatchStockRequest(BaseModel):
    symbols: List[str]
    cache_ttl: int = 86400  # 24 horas por defecto


@router.post(
    "/stocks/batch",
    response_model=List[StockInfo],
    tags=["acciones"]
)
@limiter.limit("30/minute")
async def get_stocks_batch(
    request: Request,
    body: BatchStockRequest,
    db: AsyncSession = Depends(get_db)
):
    """Obtiene múltiples acciones en una sola petición.
    
    Usa cache con TTL de 24 horas por defecto.
    Escalable para múltiples símbolos.
    """
    results = []
    unique_symbols = list(set(body.symbols))[:50]  # Máximo 50 símbolos
    
    async with AlphaVantageService() as service:
        for symbol in unique_symbols:
            try:
                stock_data = await service.get_stock_price_batch(symbol, db, body.cache_ttl)
                results.append(stock_data)
            except Exception as e:
                # Si falla, continuar con los demás
                results.append({
                    "symbol": symbol.upper(),
                    "error": str(e)
                })
    
    return results


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


@router.get(
    "/exchange-rates/multi",
    tags=["moneda"]
)
@limiter.limit(stocks_rate_limit)
async def get_multi_exchange_rates(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    async with ExchangeRateService() as service:
        rates = await service.get_multi_exchange_rates(
            [("USD", "COP"), ("EUR", "COP")],
            db
        )
        
        usd_cop = rates.get("USD_COP", {})
        eur_cop = rates.get("EUR_COP", {})
        
        usd_change = None
        eur_change = None
        
        if usd_cop.get("history") and len(usd_cop["history"]) >= 2:
            old_rate = usd_cop["history"][-2]["rate"]
            new_rate = usd_cop["today"]
            usd_change = ((new_rate - old_rate) / old_rate) * 100
        
        if eur_cop.get("history") and len(eur_cop["history"]) >= 2:
            old_rate = eur_cop["history"][-2]["rate"]
            new_rate = eur_cop["today"]
            eur_change = ((new_rate - old_rate) / old_rate) * 100
        
        return {
            "usd_cop": {
                "rate": usd_cop.get("today"),
                "change_percent": round(usd_change, 2) if usd_change else None,
                "history": usd_cop.get("history", []),
                "timestamp": usd_cop.get("timestamp")
            },
            "eur_cop": {
                "rate": eur_cop.get("today"),
                "change_percent": round(eur_change, 2) if eur_change else None,
                "history": eur_cop.get("history", []),
                "timestamp": eur_cop.get("timestamp")
            }
        }