from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging
import httpx
import json
import asyncio

from app.services.cache_service import CacheService
from app.core.api_keys import ApiKeys
from app.core.exceptions import CustomException
from app.core.config import settings

logger = logging.getLogger(__name__)


class FinnhubService:
    BASE_URL = "https://finnhub.io/api/v1"
    
    def __init__(self):
        self.api_key = ApiKeys.FINNHUB
        self.http_client = None
    
    async def __aenter__(self):
        self.http_client = httpx.AsyncClient(timeout=30.0)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.http_client:
            await self.http_client.aclose()
    
    async def get_stock_price_batch(self, symbol: str, db_session, ttl_seconds: int = 86400) -> Dict[str, Any]:
        cached = await CacheService.get(db_session, "stock", symbol)
        if cached:
            logger.info(f"Cache hit para {symbol}")
            return cached
        
        if not self.api_key:
            logger.warning(f"No hay API key de Finnhub, usando datos simulados")
            return self._get_mock_data(symbol)
        
        try:
            url = f"{self.BASE_URL}/quote"
            params = {
                "symbol": symbol.upper(),
                "token": self.api_key
            }
            
            response = await self.http_client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if "error" in data:
                logger.warning(f"Finnhub error para {symbol}: {data.get('error')}")
                return await self._get_fallback_data(symbol, db_session)

            if data.get("c") == 0 and data.get("d") is None:
                logger.warning(f"Finnhub sin datos para {symbol}")
                return await self._get_fallback_data(symbol, db_session)
            
            dp_value = data.get("dp", 0)
            result = {
                "symbol": symbol.upper(),
                "price": data.get("c", 0),
                "change": data.get("d", 0),
                "change_percent": f"{dp_value:.2f}%" if dp_value is not None else "0%",
                "volume": 0,
                "high": data.get("h", 0),
                "low": data.get("l", 0),
                "open": data.get("o", 0),
                "previous_close": data.get("pc", 0),
                "timestamp": datetime.fromtimestamp(data.get("t", 0)).isoformat() if data.get("t") else datetime.utcnow().isoformat(),
                "source": "Finnhub",
                "last_trading_day": datetime.fromtimestamp(data.get("t", 0)).strftime("%Y-%m-%d") if data.get("t") else datetime.utcnow().strftime("%Y-%m-%d")
            }
            
            await CacheService.set(
                db_session, "stock", symbol,
                value=result,
                ttl_seconds=ttl_seconds
            )
            
            return result
        
        except Exception as e:
            logger.exception(f"Error retrieving stock {symbol}")
            return await self._get_fallback_data(symbol, db_session)
    
    async def get_stock_price(self, symbol: str, db_session, ttl_seconds: int = 86400) -> Dict[str, Any]:
        return await self.get_stock_price_batch(symbol, db_session, ttl_seconds)
    
    def _get_mock_data(self, symbol: str) -> Dict[str, Any]:
        mock_prices = {
            "AAPL": 180.50, "MSFT": 410.20, "GOOGL": 145.30, 
            "AMZN": 175.40, "TSLA": 170.10, "META": 490.50, 
            "NVDA": 880.20, "NFLX": 610.30, "AMD": 160.40, "INTC": 35.20,
            "BA": 195.30, "JNJ": 155.80, "UNH": 520.40, "HD": 345.60,
            "PG": 160.20, "MA": 450.30, "DIS": 110.50, "V": 280.40,
            "KO": 62.30, "PEP": 175.80, "CSCO": 48.90, "T": 17.50,
            "ADBE": 580.20, "CRM": 290.40, "CMCSA": 45.60, "XOM": 105.30,
            "PFE": 28.40, "ORCL": 125.70, "QCOM": 165.30, "TXN": 175.80,
            "AVGO": 980.40, "COST": 625.30, "MCD": 295.60, "NKE": 105.40,
            "WMT": 165.80
        }
        price = mock_prices.get(symbol.upper(), 100.00)
        return {
            "symbol": symbol.upper(),
            "price": price,
            "change": 0.5,
            "change_percent": "0.25%",
            "volume": 1000000,
            "last_trading_day": datetime.utcnow().strftime("%Y-%m-%d"),
            "previous_close": price - 0.5,
            "source": "Mock Data (No API Key)",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def _get_fallback_data(self, symbol: str, db_session) -> Dict[str, Any]:
        from sqlalchemy import select
        from app.models.base import CacheData
        
        stmt = select(CacheData).where(CacheData.key == CacheService.generate_key("stock", symbol))
        res = await db_session.execute(stmt)
        expired_cache = res.scalar_one_or_none()
        
        if expired_cache:
            logger.info(f"Usando cache expirada como fallback para {symbol}")
            return json.loads(expired_cache.value)
        
        return self._get_mock_data(symbol)
    
    async def get_historical_data(self, symbol: str, db_session) -> Dict[str, Any]:
        cached = await CacheService.get(db_session, "historical", symbol)
        if cached:
            return cached
        
        if not self.api_key:
            raise CustomException(
                status_code=500,
                detail="API Key de Finnhub no configurada"
            )
        
        try:
            to_date = int(datetime.utcnow().timestamp())
            from_date = int((datetime.utcnow() - timedelta(days=30)).timestamp())
            
            url = f"{self.BASE_URL}/stock/candle"
            params = {
                "symbol": symbol.upper(),
                "resolution": "D",
                "from": from_date,
                "to": to_date,
                "token": self.api_key
            }
            
            response = await self.http_client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get("s") != "ok":
                raise CustomException(
                    status_code=404,
                    detail=f"Acción {symbol} no encontrada"
                )
            
            prices = []
            for i, (date, open_price, high, low, close, volume) in enumerate(
                zip(data.get("t", []), data.get("o", []), data.get("h", []), 
                    data.get("l", []), data.get("c", []), data.get("v", []))
            ):
                prices.append({
                    "date": datetime.fromtimestamp(date).strftime("%Y-%m-%d"),
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume
                })
            
            result = {
                "symbol": symbol.upper(),
                "prices": prices,
                "source": "Finnhub"
            }
            
            await CacheService.set(
                db_session, "historical", symbol,
                value=result,
                ttl_seconds=900
            )
            
            return result
        
        except httpx.HTTPError as e:
            logger.error(f"Error HTTP con Finnhub: {str(e)}")
            raise CustomException(
                status_code=503,
                detail="Error de conexión con Finnhub"
            )
        except Exception as e:
            logger.exception(f"Error retrieving historical data for {symbol}")
            raise CustomException(
                status_code=500,
                detail=f"Error al obtener datos históricos: {str(e)}"
            )


PRELOAD_STOCKS = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'NFLX', 'AMD', 'INTC',
    'BA', 'JNJ', 'UNH', 'HD', 'PG', 'MA', 'DIS', 'V', 'KO', 'PEP',
    'CSCO', 'T', 'ADBE', 'CRM', 'CMCSA', 'XOM', 'PFE', 'ORCL', 'QCOM', 'TXN',
    'AVGO', 'COST', 'MCD', 'NKE', 'WMT'
]


async def preload_all_stocks(db_session, batch_size: int = 10, delay_between_batches: float = 0.5):
    """Preload all stocks with concurrent calls for optimal performance.
    
    Args:
        db_session: Database session
        batch_size: Number of concurrent API calls (default 10)
        delay_between_batches: Delay between batches in seconds (default 0.5)
    
    Returns:
        dict with loaded and failed counts
    """
    logger.info(f"Iniciando preload de {len(PRELOAD_STOCKS)} stocks con batch_size={batch_size}")
    
    loaded_count = 0
    failed_count = 0
    
    from app.db.session import AsyncSessionLocal

    async def load_symbol(symbol: str):
        async with AsyncSessionLocal() as session:
            async with FinnhubService() as service:
                return await service.get_stock_price_batch(symbol, session, 86400)

    for i in range(0, len(PRELOAD_STOCKS), batch_size):
        batch = PRELOAD_STOCKS[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(PRELOAD_STOCKS) + batch_size - 1) // batch_size

        logger.info(f"Procesando batch {batch_num}/{total_batches}: {batch}")

        results = await asyncio.gather(
            *(load_symbol(symbol) for symbol in batch),
            return_exceptions=True
        )

        for symbol, result in zip(batch, results):
            if isinstance(result, Exception):
                failed_count += 1
                logger.error(f"Error en {symbol}: {result}")
            else:
                loaded_count += 1
                logger.info(f"Stock {symbol} cargado exitosamente")

        if i + batch_size < len(PRELOAD_STOCKS):
            await asyncio.sleep(delay_between_batches)
    
    logger.info(f"Preload completado: {loaded_count} exitosos, {failed_count} fallidos")
    return {"total": len(PRELOAD_STOCKS), "loaded": loaded_count, "failed": failed_count}


async def preload_stocks_task():
    """Task function for background preload (used by APScheduler and BackgroundTasks)."""
    from app.db.session import AsyncSessionLocal
    
    logger.info("Iniciando tarea de preload de stocks...")
    
    try:
        async with AsyncSessionLocal() as db:
            result = await preload_all_stocks(db)
            logger.info(f"Tarea de preload completada: {result}")
            return result
    except Exception as e:
        logger.error(f"Error en tarea de preload: {e}")
        return {"error": str(e)}
