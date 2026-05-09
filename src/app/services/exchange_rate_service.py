from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging
import httpx

from app.services.cache_service import CacheService
from app.core.api_keys import ApiKeys
from app.core.exceptions import CustomException
from app.core.config import settings

logger = logging.getLogger(__name__)


class ExchangeRateService:
    BASE_URL = "https://v6.exchangerate-api.com/v6"
    
    def __init__(self):
        self.api_key = ApiKeys.EXCHANGE_RATE
        self.http_client = None
    
    async def __aenter__(self):
        self.http_client = httpx.AsyncClient(timeout=30.0)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.http_client:
            await self.http_client.aclose()
    
    async def get_exchange_rate(self, from_currency: str, to_currency: str, db_session) -> Dict[str, Any]:
        cached = await CacheService.get(db_session, "exchange", from_currency, to_currency)
        if cached:
            return cached
        
        if not self.api_key:
            raise CustomException(
                status_code=500,
                detail="API Key de ExchangeRate no configurada"
            )
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/{self.api_key}/latest/{from_currency.upper()}"
                )
                response.raise_for_status()
                data = response.json()
            
            if data.get("result") != "success":
                raise CustomException(
                    status_code=400,
                    detail=f"Error en conversión de moneda: {data.get('error-type', 'error desconocido')}"
                )
            
            rates = data.get("conversion_rates", {})
            
            if to_currency.upper() not in rates:
                raise CustomException(
                    status_code=404,
                    detail=f"Moneda {to_currency.upper()} no encontrada"
                )
            
            rate = rates[to_currency.upper()]
            
            result = {
                "from_currency": from_currency.upper(),
                "to_currency": to_currency.upper(),
                "rate": rate,
                "timestamp": datetime.utcnow().isoformat(),
                "source": "ExchangeRate-API"
            }
            
            await CacheService.set(
                db_session, "exchange", from_currency, to_currency,
                value=result,
                ttl_seconds=3600
            )
            
            return result
        
        except httpx.HTTPError as e:
            logger.error(f"Error HTTP con ExchangeRate: {str(e)}")
            raise CustomException(
                status_code=503,
                detail="Error de conexión con ExchangeRate API"
            )
    
    async def convert_currency(self, amount: float, from_currency: str, 
                               to_currency: str, db_session) -> Dict[str, Any]:
        exchange = await self.get_exchange_rate(from_currency, to_currency, db_session)
        
        converted_amount = amount * exchange["rate"]
        
        return {
            "amount": amount,
            "from_currency": from_currency.upper(),
            "converted_amount": round(converted_amount, 2),
            "to_currency": to_currency.upper(),
            "rate": exchange["rate"],
            "timestamp": exchange["timestamp"]
        }
