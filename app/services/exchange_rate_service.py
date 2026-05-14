from datetime import datetime, timedelta, date
from typing import Dict, Any, Optional, List
import logging
import asyncio

import httpx

from sqlalchemy import select
from app.services.cache_service import CacheService
from app.core.api_keys import ApiKeys
from app.core.exceptions import CustomException
from app.core.config import settings
from app.models.base import ExchangeRateHistory

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]


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
    
    async def _fetch_rate_from_api(self, from_currency: str, to_currency: str) -> Optional[Dict[str, Any]]:
        response = await self.http_client.get(
            f"{self.BASE_URL}/{self.api_key}/latest/{from_currency.upper()}"
        )
        response.raise_for_status()
        data = response.json()

        if data.get("result") != "success":
            logger.error(f"ExchangeRate API error: {data.get('error-type', 'unknown')}")
            return None

        rates = data.get("conversion_rates", {})
        if to_currency.upper() not in rates:
            logger.error(f"Currency {to_currency.upper()} not found in rates")
            return None

        return {
            "from_currency": from_currency.upper(),
            "to_currency": to_currency.upper(),
            "rate": rates[to_currency.upper()],
            "timestamp": datetime.utcnow().isoformat(),
            "source": "ExchangeRate-API"
        }

    async def _get_fallback_rate(self, from_currency: str, to_currency: str, db_session) -> Optional[Dict[str, Any]]:
        stmt = select(ExchangeRateHistory).where(
            ExchangeRateHistory.from_currency == from_currency.upper(),
            ExchangeRateHistory.to_currency == to_currency.upper()
        ).order_by(ExchangeRateHistory.date.desc()).limit(1)

        result = await db_session.execute(stmt)
        historical = result.scalar_one_or_none()

        if historical:
            logger.warning(f"Using historical fallback for {from_currency}/{to_currency}: {historical.rate}")
            return {
                "from_currency": from_currency.upper(),
                "to_currency": to_currency.upper(),
                "rate": float(historical.rate),
                "timestamp": datetime.utcnow().isoformat(),
                "source": "ExchangeRate-Historical-Fallback"
            }

        return None

    async def get_exchange_rate(self, from_currency: str, to_currency: str, db_session) -> Dict[str, Any]:
        cached = await CacheService.get(db_session, "exchange", from_currency, to_currency)
        if cached:
            return cached

        if not self.api_key:
            raise CustomException(
                status_code=500,
                detail="API Key de ExchangeRate no configurada"
            )

        for attempt in range(MAX_RETRIES):
            try:
                result = await self._fetch_rate_from_api(from_currency, to_currency)
                if result:
                    await CacheService.set(
                        db_session, "exchange", from_currency, to_currency,
                        value=result,
                        ttl_seconds=86400
                    )
                    return result
            except httpx.HTTPError as e:
                logger.warning(f"ExchangeRate attempt {attempt + 1}/{MAX_RETRIES} failed: {str(e)}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAYS[attempt])
                continue

        fallback = await self._get_fallback_rate(from_currency, to_currency, db_session)
        if fallback:
            await CacheService.set(
                db_session, "exchange", from_currency, to_currency,
                value=fallback,
                ttl_seconds=3600
            )
            return fallback

        raise CustomException(
            status_code=503,
            detail="Error de conexión con ExchangeRate API y no hay datos históricos disponibles"
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

    async def save_exchange_rate(self, from_currency: str, to_currency: str, rate: float, db_session) -> None:
        today = date.today()
        
        stmt = select(ExchangeRateHistory).where(
            ExchangeRateHistory.from_currency == from_currency.upper(),
            ExchangeRateHistory.to_currency == to_currency.upper(),
            ExchangeRateHistory.date == today
        )
        result = await db_session.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            existing.rate = rate
        else:
            new_rate = ExchangeRateHistory(
                from_currency=from_currency.upper(),
                to_currency=to_currency.upper(),
                rate=rate,
                date=today
            )
            db_session.add(new_rate)
        
        await db_session.flush()

    async def get_exchange_history(self, from_currency: str, to_currency: str, days: int, db_session) -> List[Dict[str, Any]]:
        start_date = date.today() - timedelta(days=days)
        
        stmt = select(ExchangeRateHistory).where(
            ExchangeRateHistory.from_currency == from_currency.upper(),
            ExchangeRateHistory.to_currency == to_currency.upper(),
            ExchangeRateHistory.date >= start_date
        ).order_by(ExchangeRateHistory.date.asc())
        
        result = await db_session.execute(stmt)
        rates = result.scalars().all()
        
        return [
            {
                "date": str(r.date),
                "rate": float(r.rate)
            }
            for r in rates
        ]

    async def get_multi_exchange_rates(self, pairs: List[tuple], db_session) -> Dict[str, Any]:
        result = {}

        for from_curr, to_curr in pairs:
            current_rate = await self.get_exchange_rate(from_curr, to_curr, db_session)
            await self.save_exchange_rate(from_curr, to_curr, current_rate["rate"], db_session)

            history = await self.get_exchange_history(from_curr, to_curr, 7, db_session)

            result[f"{from_curr}_{to_curr}"] = {
                "today": current_rate["rate"],
                "history": history,
                "timestamp": current_rate["timestamp"]
            }

        return result


EXCHANGE_PAIRS = [
    ("USD", "COP"), ("EUR", "COP"), ("USD", "MXN"),
    ("USD", "BRL"), ("USD", "CLP"), ("USD", "PEN"),
    ("USD", "ARS"), ("EUR", "USD"), ("GBP", "USD"), ("USD", "JPY")
]


async def preload_exchange_rates_task():
    """Task function for background preload of exchange rates (used by APScheduler and startup)."""
    from app.db.session import AsyncSessionLocal

    logger.info("Iniciando tarea de preload de tasas de cambio...")

    try:
        async with AsyncSessionLocal() as db:
            async with ExchangeRateService() as service:
                for from_curr, to_curr in EXCHANGE_PAIRS:
                    try:
                        rate = await service.get_exchange_rate(from_curr, to_curr, db)
                        await service.save_exchange_rate(from_curr, to_curr, rate["rate"], db)
                        logger.info(f"Tasa {from_curr}/{to_curr} pre-cargada: {rate['rate']}")
                    except Exception as e:
                        logger.error(f"Error pre-cargando {from_curr}/{to_curr}: {e}")

                await db.commit()
                logger.info("Tarea de preload de tasas de cambio completada")
                return {"status": "completed", "pairs": len(EXCHANGE_PAIRS)}
    except Exception as e:
        logger.error(f"Error en tarea de preload de tasas de cambio: {e}")
        return {"error": str(e)}
