from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import logging
import httpx
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.services.cache_service import CacheService
from app.models.base import WorldIndex, IndexHistory

logger = logging.getLogger(__name__)


WORLD_INDICES = [
    {"symbol": "^GSPC", "name": "S&P 500", "country": "US", "region": "North America", "currency": "USD"},
    {"symbol": "^DJI", "name": "Dow Jones Industrial", "country": "US", "region": "North America", "currency": "USD"},
    {"symbol": "^IXIC", "name": "NASDAQ Composite", "country": "US", "region": "North America", "currency": "USD"},
    {"symbol": "^RUT", "name": "Russell 2000", "country": "US", "region": "North America", "currency": "USD"},
    {"symbol": "^MXX", "name": "IPC México", "country": "MX", "region": "North America", "currency": "MXN"},
    {"symbol": "^IBOV", "name": "IBOVESPA", "country": "BR", "region": "South America", "currency": "BRL"},
    {"symbol": "^MERV", "name": "MERVAL", "country": "AR", "region": "South America", "currency": "ARS"},
    {"symbol": "^COLCAP", "name": "COLCAP", "country": "CO", "region": "South America", "currency": "COP"},
    {"symbol": "^IPSA", "name": "IPSA Chile", "country": "CL", "region": "South America", "currency": "CLP"},
    {"symbol": "^BVSN", "name": "IBVL Perú", "country": "PE", "region": "South America", "currency": "PEN"},
    {"symbol": "^FTSE", "name": "FTSE 100", "country": "GB", "region": "Europe", "currency": "GBP"},
    {"symbol": "^GDAXI", "name": "DAX", "country": "DE", "region": "Europe", "currency": "EUR"},
    {"symbol": "^FCHI", "name": "CAC 40", "country": "FR", "region": "Europe", "currency": "EUR"},
    {"symbol": "^IBEX", "name": "IBEX 35", "country": "ES", "region": "Europe", "currency": "EUR"},
    {"symbol": "^STOXX50E", "name": "STOXX Europe 50", "country": "EU", "region": "Europe", "currency": "EUR"},
    {"symbol": "^N225", "name": "Nikkei 225", "country": "JP", "region": "Asia", "currency": "JPY"},
    {"symbol": "^HSI", "name": "Hang Seng", "country": "HK", "region": "Asia", "currency": "HKD"},
    {"symbol": "^SSEC", "name": "Shanghai Composite", "country": "CN", "region": "Asia", "currency": "CNY"},
    {"symbol": "^BSESN", "name": "BSE Sensex", "country": "IN", "region": "Asia", "currency": "INR"},
    {"symbol": "^KS11", "name": "KOSPI", "country": "KR", "region": "Asia", "currency": "KRW"},
    {"symbol": "^AXJO", "name": "ASX 200", "country": "AU", "region": "Oceania", "currency": "AUD"},
    {"symbol": "^NZE", "name": "NZX 50", "country": "NZ", "region": "Oceania", "currency": "NZD"},
    {"symbol": "MSCI.WORLD", "name": "MSCI World", "country": "WW", "region": "Global", "currency": "USD"},
    {"symbol": "EEM", "name": "MSCI Emerging Markets", "country": "EM", "region": "Global", "currency": "USD"},
]

MOCK_INDICES = {
    "^GSPC": {"price": 5850.25, "change": 15.50, "change_percent": 0.27},
    "^DJI": {"price": 42850.80, "change": -45.20, "change_percent": -0.11},
    "^IXIC": {"price": 18560.40, "change": 85.30, "change_percent": 0.46},
    "^MXX": {"price": 52780.50, "change": 320.15, "change_percent": 0.61},
    "^IBOV": {"price": 128750.20, "change": -580.30, "change_percent": -0.45},
    "^MERV": {"price": 1850000.00, "change": 12500.00, "change_percent": 0.68},
    "^COLCAP": {"price": 1450.80, "change": 8.50, "change_percent": 0.59},
    "^IPSA": {"price": 5800.50, "change": -15.20, "change_percent": -0.26},
    "^BVSN": {"price": 650.25, "change": 3.80, "change_percent": 0.59},
    "^FTSE": {"price": 8450.30, "change": 25.60, "change_percent": 0.30},
    "^GDAXI": {"price": 18950.40, "change": -35.80, "change_percent": -0.19},
    "^FCHI": {"price": 7850.20, "change": 45.30, "change_percent": 0.58},
    "^IBEX": {"price": 11250.80, "change": 65.40, "change_percent": 0.58},
    "^N225": {"price": 39850.50, "change": -120.30, "change_percent": -0.30},
    "^HSI": {"price": 18560.25, "change": 250.80, "change_percent": 1.37},
    "^SSEC": {"price": 3420.80, "change": 15.50, "change_percent": 0.45},
    "^BSESN": {"price": 78500.40, "change": -180.20, "change_percent": -0.23},
    "^KS11": {"price": 2850.60, "change": 25.40, "change_percent": 0.90},
    "^AXJO": {"price": 7850.20, "change": 35.80, "change_percent": 0.46},
    "MSCI.WORLD": {"price": 3850.40, "change": 12.30, "change_percent": 0.32},
    "EEM": {"price": 45.80, "change": -0.25, "change_percent": -0.54},
}


class WorldIndicesService:
    def __init__(self):
        self.http_client = None
        self.finnhub_key = None
    
    async def __aenter__(self):
        self.http_client = httpx.AsyncClient(timeout=30.0)
        from app.core.api_keys import ApiKeys
        self.finnhub_key = ApiKeys.FINNHUB
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.http_client:
            await self.http_client.aclose()
    
    async def get_indices(self, db: AsyncSession) -> List[Dict[str, Any]]:
        cached = await CacheService.get(db, "world_indices", "all")
        if cached:
            return cached
        
        result = []
        
        for idx_data in WORLD_INDICES:
            index_info = await self._get_index_data(idx_data["symbol"], db)
            result.append({
                "symbol": idx_data["symbol"],
                "name": idx_data["name"],
                "country": idx_data["country"],
                "region": idx_data["region"],
                "currency": idx_data["currency"],
                **index_info
            })
        
        await CacheService.set(
            db, "world_indices", "all",
            value=result,
            ttl_seconds=3600
        )
        
        return result
    
    async def _get_index_data(self, symbol: str, db: AsyncSession) -> Dict[str, Any]:
        mock = MOCK_INDICES.get(symbol, {"price": 0, "change": 0, "change_percent": 0})
        
        if self.finnhub_key and symbol in ["^GSPC", "^DJI", "^IXIC"]:
            try:
                url = "https://finnhub.io/api/v1/quote"
                params = {"symbol": symbol, "token": self.finnhub_key}
                response = await self.http_client.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("c", 0) > 0:
                        return {
                            "current_value": data.get("c", mock["price"]),
                            "change": data.get("d", mock["change"]),
                            "change_percent": round(data.get("dp", mock["change_percent"]), 2),
                            "high": data.get("h", mock["price"]),
                            "low": data.get("l", mock["price"]),
                            "previous_close": data.get("pc", mock["price"]),
                            "last_updated": datetime.utcnow().isoformat()
                        }
            except Exception as e:
                logger.warning(f"Error fetching {symbol} from Finnhub: {e}")
        
        return {
            "current_value": mock["price"],
            "change": mock["change"],
            "change_percent": mock["change_percent"],
            "high": mock["price"] * 1.01,
            "low": mock["price"] * 0.99,
            "previous_close": mock["price"] - mock["change"],
            "last_updated": datetime.utcnow().isoformat()
        }
    
    async def get_index_by_symbol(self, symbol: str, db: AsyncSession) -> Optional[Dict[str, Any]]:
        idx_data = next((i for i in WORLD_INDICES if i["symbol"] == symbol), None)
        if not idx_data:
            return None
        
        index_info = await self._get_index_data(symbol, db)
        return {
            "symbol": idx_data["symbol"],
            "name": idx_data["name"],
            "country": idx_data["country"],
            "region": idx_data["region"],
            "currency": idx_data["currency"],
            **index_info
        }
    
    async def get_indices_by_region(self, region: str, db: AsyncSession) -> List[Dict[str, Any]]:
        indices = await self.get_indices(db)
        return [idx for idx in indices if idx.get("region") == region]
    
    async def initialize_indices_db(self, db: AsyncSession) -> Dict[str, Any]:
        created = 0
        updated = 0
        
        for idx_data in WORLD_INDICES:
            stmt = select(WorldIndex).where(WorldIndex.symbol == idx_data["symbol"])
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                existing.name = idx_data["name"]
                existing.country = idx_data["country"]
                existing.region = idx_data["region"]
                existing.currency = idx_data["currency"]
                updated += 1
            else:
                new_index = WorldIndex(
                    symbol=idx_data["symbol"],
                    name=idx_data["name"],
                    country=idx_data["country"],
                    region=idx_data["region"],
                    currency=idx_data["currency"]
                )
                db.add(new_index)
                created += 1
        
        await db.flush()
        return {"created": created, "updated": updated}


async def preload_world_indices(db: AsyncSession):
    async with WorldIndicesService() as service:
        return await service.initialize_indices_db(db)