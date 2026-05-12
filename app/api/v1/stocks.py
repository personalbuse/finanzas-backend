from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from pydantic import BaseModel, Field, field_validator
import logging

from app.core.rate_limiter import limiter, stocks_rate_limit
from app.core.security import require_admin_api_key
from app.db.session import get_db
from app.services.finnhub_service import FinnhubService, preload_stocks_task, preload_all_stocks
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

# Variable global para indicar que el código fue deployado correctamente
PRELOAD_VERIFIED = True


@router.post("/stocks/preload", tags=["admin"], dependencies=[Depends(require_admin_api_key)])
async def preload_stocks_NEWVERSION(db: AsyncSession = Depends(get_db)):
    """Endpoint para precargar todos los stocks en cache.
    
    Versión optimizada con llamadas concurrentes (batch de 10).
    ~20 segundos para 35 stocks en vez de ~35 segundos.
    """
    logger.info(f"NUEVA VERSION - Iniciando precarga optimizada de {len(PRELOAD_STOCKS)} stocks...")
    
    result = await preload_all_stocks(db, batch_size=10, delay_between_batches=0.5)
    logger.info(f"Precarga completada: {result}")
    
    return result


@router.post("/stocks/refresh", tags=["admin"], dependencies=[Depends(require_admin_api_key)])
async def refresh_stocks_background(background_tasks: BackgroundTasks):
    """Endpoint para iniciar actualización de stocks en background.
    
    El usuario no espera - la actualización corre en background.
    Uso desde frontend cuando el usuario entra a la sección de stocks.
    """
    logger.info("Solicitud de refresh de stocks recibida - ejecutando en background")
    background_tasks.add_task(preload_stocks_task)
    return {
        "message": "Actualización de stocks iniciada en background",
        "status": "processing"
    }


@router.post("/stocks/refresh-sync", tags=["admin"], dependencies=[Depends(require_admin_api_key)])
async def refresh_stocks_sync(db: AsyncSession = Depends(get_db)):
    """Endpoint para actualizar stocks de forma síncrona (para testing).
    
    Retorna cuando completa la actualización (~20 segundos con batch de 10).
    """
    logger.info("Solicitud de refresh síncrona de stocks")
    result = await preload_all_stocks(db, batch_size=10, delay_between_batches=0.5)
    return {
        "message": "Actualización de stocks completada",
        "result": result
    }


class BatchStockRequest(BaseModel):
    symbols: List[str] = Field(..., min_length=1, max_length=50)
    cache_ttl: int = Field(default=86400, ge=60, le=86400)

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, symbols: List[str]) -> List[str]:
        cleaned = []
        for symbol in symbols:
            normalized = symbol.strip().upper()
            if not normalized or len(normalized) > 10:
                continue
            if not all(ch.isalnum() or ch in ".-" for ch in normalized):
                continue
            cleaned.append(normalized)
        if not cleaned:
            raise ValueError("Debes enviar al menos un símbolo válido")
        return cleaned


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
    unique_symbols = []
    for symbol in body.symbols:
        cleaned = symbol.strip().upper()
        if cleaned and cleaned not in unique_symbols:
            unique_symbols.append(cleaned)
    
    async with FinnhubService() as service:
        for symbol in unique_symbols:
            try:
                stock_data = await service.get_stock_price_batch(symbol, db, body.cache_ttl)
                results.append(stock_data)
            except Exception as e:
                logger.warning(f"No se pudo cargar {symbol}: {e}")
                results.append(service._get_mock_data(symbol))
    
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
    async with FinnhubService() as service:
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
    async with FinnhubService() as service:
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
    if amount < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El monto debe ser mayor o igual a cero",
        )

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
