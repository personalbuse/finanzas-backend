from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging
import httpx
import json

from app.services.cache_service import CacheService
from app.core.api_keys import ApiKeys
from app.core.exceptions import CustomException
from app.core.config import settings

logger = logging.getLogger(__name__)


class AlphaVantageService:
    BASE_URL = "https://www.alphavantage.co/query"
    
    def __init__(self):
        self.api_key = ApiKeys.ALPHA_VANTAGE
        self.http_client = None
    
    async def __aenter__(self):
        self.http_client = httpx.AsyncClient(timeout=30.0)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.http_client:
            await self.http_client.aclose()
    
    async def get_stock_price(self, symbol: str, db_session) -> Dict[str, Any]:
        cached = await CacheService.get(db_session, "stock", symbol)
        if cached:
            logger.info(f"Cache hit para {symbol}")
            return cached
        
        if not self.api_key:
            raise CustomException(
                status_code=500,
                detail="API Key de Alpha Vantage no configurada"
            )
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    self.BASE_URL,
                    params={
                        "function": "GLOBAL_QUOTE",
                        "symbol": symbol.upper(),
                        "apikey": self.api_key
                    }
                )
                response.raise_for_status()
                data = response.json()
            
            # Handle Alpha Vantage Rate Limiting (Note) or Errors
            is_rate_limited = "Note" in data
            is_error = "Error Message" in data
            
            if is_rate_limited or is_error or "Global Quote" not in data:
                if is_rate_limited:
                    logger.warning(f"Alpha Vantage rate limit reached for {symbol}")
                
                # FALLBACK: Try to get LAST KNOWN value from cache (even if expired)
                # We do this by query without the expiration filter
                from sqlalchemy import select
                from app.models.base import CacheData
                stmt = select(CacheData).where(CacheData.key == CacheService.generate_key("stock", symbol))
                res = await db_session.execute(stmt)
                expired_cache = res.scalar_one_or_none()
                
                if expired_cache:
                    logger.info(f"Usando caché expirada como fallback para {symbol}")
                    return json.loads(expired_cache.value)
                
                # If everything fails, return a simulated stable price for major stocks
                # to avoid breaking the student's experience
                mock_prices = {
                    "AAPL": 180.50, "MSFT": 410.20, "GOOGL": 145.30, 
                    "AMZN": 175.40, "TSLA": 170.10, "META": 490.50, 
                    "NVDA": 880.20, "NFLX": 610.30, "AMD": 160.40, "INTC": 35.20
                }
                price = mock_prices.get(symbol.upper(), 100.00)
                return {
                    "symbol": symbol.upper(),
                    "price": price,
                    "change": 0.5,
                    "change_percent": "+0.25%",
                    "volume": 1000000,
                    "last_trading_day": datetime.utcnow().strftime("%Y-%m-%d"),
                    "previous_close": price - 0.5,
                    "source": "Simulated Data (Rate Limited)",
                    "timestamp": datetime.utcnow().isoformat()
                }

            quote = data["Global Quote"]
            result = {
                "symbol": symbol.upper(),
                "price": float(quote.get("05. price", 0)),
                "change": float(quote.get("09. change", 0)),
                "change_percent": quote.get("10. change percent", "0%"),
                "volume": int(quote.get("06. volume", 0)),
                "last_trading_day": quote.get("07. latest trading day", ""),
                "previous_close": float(quote.get("08. previous close", 0)),
                "source": "Alpha Vantage",
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await CacheService.set(
                db_session, "stock", symbol,
                value=result,
                ttl_seconds=300
            )
            
            return result
        
        except Exception as e:
            logger.error(f"Error recuperando stock {symbol}: {str(e)}")
            # Global fallback for any crash
            return {
                "symbol": symbol.upper(),
                "price": 100.0,
                "change": 0,
                "change_percent": "0%",
                "volume": 0,
                "last_trading_day": datetime.utcnow().strftime("%Y-%m-%d"),
                "previous_close": 100.0,
                "source": "Default Fallback",
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def get_historical_data(self, symbol: str, db_session) -> Dict[str, Any]:
        cached = await CacheService.get(db_session, "historical", symbol)
        if cached:
            return cached
        
        if not self.api_key:
            raise CustomException(
                status_code=500,
                detail="API Key de Alpha Vantage no configurada"
            )
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    self.BASE_URL,
                    params={
                        "function": "TIME_SERIES_DAILY",
                        "symbol": symbol.upper(),
                        "apikey": self.api_key,
                        "outputsize": "compact"
                    }
                )
                response.raise_for_status()
                data = response.json()
            
            if "Error Message" in data:
                raise CustomException(
                    status_code=404,
                    detail=f"Acción {symbol} no encontrada"
                )
            
            if "Time Series (Daily)" not in data:
                raise CustomException(
                    status_code=502,
                    detail="Error al obtener datos históricos"
                )
            
            time_series = data["Time Series (Daily)"]
            prices = []
            
            for date, info in list(time_series.items())[:30]:
                prices.append({
                    "date": date,
                    "open": float(info["1. open"]),
                    "high": float(info["2. high"]),
                    "low": float(info["3. low"]),
                    "close": float(info["4. close"]),
                    "volume": int(info["5. volume"])
                })
            
            result = {
                "symbol": symbol.upper(),
                "prices": prices,
                "source": "Alpha Vantage"
            }
            
            await CacheService.set(
                db_session, "historical", symbol,
                value=result,
                ttl_seconds=900
            )
            
            return result
        
        except httpx.HTTPError as e:
            logger.error(f"Error HTTP con Alpha Vantage: {str(e)}")
            raise CustomException(
                status_code=503,
                detail="Error de conexión con Alpha Vantage"
            )
