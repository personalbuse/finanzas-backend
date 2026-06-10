import logging
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import InternationalStock
from app.services.cache_service import CacheService

logger = logging.getLogger(__name__)


REGIONAL_STOCKS = {
    "US": [
        {"symbol": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "sector": "Technology", "currency": "USD"},
        {"symbol": "MSFT", "name": "Microsoft Corp.", "exchange": "NASDAQ", "sector": "Technology", "currency": "USD"},
        {"symbol": "GOOGL", "name": "Alphabet Inc.", "exchange": "NASDAQ", "sector": "Technology", "currency": "USD"},
        {"symbol": "AMZN", "name": "Amazon.com Inc.", "exchange": "NASDAQ", "sector": "Consumer", "currency": "USD"},
        {"symbol": "TSLA", "name": "Tesla Inc.", "exchange": "NASDAQ", "sector": "Automotive", "currency": "USD"},
        {"symbol": "META", "name": "Meta Platforms", "exchange": "NASDAQ", "sector": "Technology", "currency": "USD"},
        {"symbol": "NVDA", "name": "NVIDIA Corp.", "exchange": "NASDAQ", "sector": "Technology", "currency": "USD"},
        {"symbol": "BRK.B", "name": "Berkshire Hathaway", "exchange": "NYSE", "sector": "Financial", "currency": "USD"},
        {"symbol": "JPM", "name": "JPMorgan Chase", "exchange": "NYSE", "sector": "Financial", "currency": "USD"},
        {"symbol": "V", "name": "Visa Inc.", "exchange": "NYSE", "sector": "Financial", "currency": "USD"},
    ],
    "MX": [
        {"symbol": "AMX", "name": "América Móvil", "exchange": "BMV", "sector": "Telecom", "currency": "MXN"},
        {"symbol": "GMEXICO", "name": "Grupo México", "exchange": "BMV", "sector": "Industrial", "currency": "MXN"},
        {"symbol": "CEMEX", "name": "CEMEX CPO", "exchange": "BMV", "sector": "Materials", "currency": "MXN"},
        {"symbol": "WALMEX", "name": "Walmart de México", "exchange": "BMV", "sector": "Retail", "currency": "MXN"},
        {"symbol": "TLEVISAB", "name": "Televisa CPO", "exchange": "BMV", "sector": "Media", "currency": "MXN"},
        {"symbol": "AC", "name": "Arca Continental", "exchange": "BMV", "sector": "Consumer", "currency": "MXN"},
        {"symbol": "ASUR", "name": "ASUR", "exchange": "BMV", "sector": "Infrastructure", "currency": "MXN"},
        {"symbol": "KIMBER", "name": "Kimberly-Clark", "exchange": "BMV", "sector": "Consumer", "currency": "MXN"},
    ],
    "BR": [
        {"symbol": "PETR4.SA", "name": "Petrobras", "exchange": "BOVESPA", "sector": "Energy", "currency": "BRL"},
        {"symbol": "VALE3.SA", "name": "Vale", "exchange": "BOVESPA", "sector": "Materials", "currency": "BRL"},
        {"symbol": "ITUB4.SA", "name": "Itaú Unibanco", "exchange": "BOVESPA", "sector": "Financial", "currency": "BRL"},
        {"symbol": "BBDC4.SA", "name": "Bradesco", "exchange": "BOVESPA", "sector": "Financial", "currency": "BRL"},
        {"symbol": "ABEV3.SA", "name": "Ambev", "exchange": "BOVESPA", "sector": "Consumer", "currency": "BRL"},
        {"symbol": "WEGE3.SA", "name": "WEG", "exchange": "BOVESPA", "sector": "Industrial", "currency": "BRL"},
        {"symbol": "PETR3.SA", "name": "Petrobras PN", "exchange": "BOVESPA", "sector": "Energy", "currency": "BRL"},
        {"symbol": "BBAS3.SA", "name": "Banco do Brasil", "exchange": "BOVESPA", "sector": "Financial", "currency": "BRL"},
    ],
    "CO": [
        {"symbol": "ECOPETROL", "name": "Ecopetrol", "exchange": "BVC", "sector": "Energy", "currency": "COP"},
        {"symbol": "BANCOLOMBIA", "name": "Bancolombia", "exchange": "BVC", "sector": "Financial", "currency": "COP"},
        {"symbol": "CEMEXCOS", "name": "CEMEX Colombia", "exchange": "BVC", "sector": "Materials", "currency": "COP"},
        {"symbol": "GRUPOAV", "name": "Grupo Argos", "exchange": "BVC", "sector": "Conglomerate", "currency": "COP"},
        {"symbol": "NUTRESA", "name": "Grupo Nutresa", "exchange": "BVC", "sector": "Consumer", "currency": "COP"},
        {"symbol": "ISA", "name": "ISA", "exchange": "BVC", "sector": "Utilities", "currency": "COP"},
    ],
    "CL": [
        {"symbol": "LTM.SN", "name": "LATAM Airlines", "exchange": "BCS", "sector": "Transportation", "currency": "CLP"},
        {"symbol": "ENELAM.SN", "name": "Enel Chile", "exchange": "BCS", "sector": "Utilities", "currency": "CLP"},
        {"symbol": "CCU.SN", "name": "CCU", "exchange": "BCS", "sector": "Consumer", "currency": "CLP"},
        {"symbol": "SQM-B.SN", "name": "SQM", "exchange": "BCS", "sector": "Materials", "currency": "CLP"},
        {"symbol": "COPEC.SN", "name": "Copec", "exchange": "BCS", "sector": "Energy", "currency": "CLP"},
    ],
    "GB": [
        {"symbol": "HSBA.L", "name": "HSBC Holdings", "exchange": "LSE", "sector": "Financial", "currency": "GBP"},
        {"symbol": "BP.L", "name": "BP PLC", "exchange": "LSE", "sector": "Energy", "currency": "GBP"},
        {"symbol": "SHEL.L", "name": "Shell", "exchange": "LSE", "sector": "Energy", "currency": "GBP"},
        {"symbol": "AZN.L", "name": "AstraZeneca", "exchange": "LSE", "sector": "Healthcare", "currency": "GBP"},
        {"symbol": "ULVR.L", "name": "Unilever", "exchange": "LSE", "sector": "Consumer", "currency": "GBP"},
        {"symbol": "GSK.L", "name": "GSK", "exchange": "LSE", "sector": "Healthcare", "currency": "GBP"},
    ],
    "DE": [
        {"symbol": "SAP.DE", "name": "SAP SE", "exchange": "XETRA", "sector": "Technology", "currency": "EUR"},
        {"symbol": "SIE.DE", "name": "Siemens", "exchange": "XETRA", "sector": "Industrial", "currency": "EUR"},
        {"symbol": "BAS.DE", "name": "BASF", "exchange": "XETRA", "sector": "Materials", "currency": "EUR"},
        {"symbol": "BMW.DE", "name": "BMW", "exchange": "XETRA", "sector": "Automotive", "currency": "EUR"},
        {"symbol": "VOW3.DE", "name": "Volkswagen", "exchange": "XETRA", "sector": "Automotive", "currency": "EUR"},
    ],
    "FR": [
        {"symbol": "MC.PA", "name": "LVMH", "exchange": "EURONEXT", "sector": "Consumer", "currency": "EUR"},
        {"symbol": "OR.PA", "name": "L'Oréal", "exchange": "EURONEXT", "sector": "Consumer", "currency": "EUR"},
        {"symbol": "TEF.PA", "name": "TotalEnergies", "exchange": "EURONEXT", "sector": "Energy", "currency": "EUR"},
        {"symbol": "SAN.PA", "name": "Sanofi", "exchange": "EURONEXT", "sector": "Healthcare", "currency": "EUR"},
    ],
    "JP": [
        {"symbol": "7203.T", "name": "Toyota Motor", "exchange": "TSE", "sector": "Automotive", "currency": "JPY"},
        {"symbol": "9984.T", "name": "SoftBank", "exchange": "TSE", "sector": "Financial", "currency": "JPY"},
        {"symbol": "6758.T", "name": "Sony Group", "exchange": "TSE", "sector": "Technology", "currency": "JPY"},
        {"symbol": "9432.T", "name": "NTT Docomo", "exchange": "TSE", "sector": "Telecom", "currency": "JPY"},
        {"symbol": "8031.T", "name": "Mitsubishi UFJ", "exchange": "TSE", "sector": "Financial", "currency": "JPY"},
    ],
    "CN": [
        {"symbol": "600519.SS", "name": "Kweichow Moutai", "exchange": "SSE", "sector": "Consumer", "currency": "CNY"},
        {"symbol": "BABA.SS", "name": "Alibaba", "exchange": "SSE", "sector": "Consumer", "currency": "CNY"},
        {"symbol": "601398.SS", "name": "ICBC", "exchange": "SSE", "sector": "Financial", "currency": "CNY"},
        {"symbol": "600036.SS", "name": "China Merchants", "exchange": "SSE", "sector": "Financial", "currency": "CNY"},
    ],
}

MOCK_PRICES = {
    "AMX": 15.80,
    "GMEXICO": 180.50,
    "CEMEX": 15.20,
    "WALMEX": 68.50,
    "TLEVISAB": 10.50,
    "ECOPETROL": 2850.00,
    "BANCOLOMBIA": 42000.00,
    "LTM.SN": 8500.00,
    "ENELAM": 120.50,
    "HSBA.L": 645.50,
    "BP.L": 520.30,
    "SHEL.L": 2850.00,
    "SAP.DE": 185.50,
    "SIE.DE": 195.80,
    "7203.T": 2850.00,
    "600519.SS": 1850.50,
}


class InternationalStocksService:
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

    async def get_stocks_by_region(self, region: str, db: AsyncSession) -> list[dict[str, Any]]:
        cached = await CacheService.get(db, "international_stocks", region)
        if cached:
            return cached

        country_map = {
            "North America": ["US", "MX"],
            "South America": ["BR", "CO", "CL"],
            "Europe": ["GB", "DE", "FR"],
            "Asia": ["JP", "CN"]
        }

        countries = country_map.get(region, [])
        result = []

        for country in countries:
            stocks = REGIONAL_STOCKS.get(country, [])
            for stock in stocks:
                price_data = await self._get_stock_price(stock["symbol"], db)
                result.append({
                    **stock,
                    "country": country,
                    "region": region,
                    **price_data
                })

        await CacheService.set(
            db, "international_stocks", region,
            value=result,
            ttl_seconds=3600
        )

        return result

    async def get_all_regions(self, db: AsyncSession) -> dict[str, list[dict[str, Any]]]:
        regions = {
            "North America": ["US", "MX"],
            "South America": ["BR", "CO", "CL"],
            "Europe": ["GB", "DE", "FR"],
            "Asia": ["JP", "CN"]
        }

        result = {}
        for region, countries in regions.items():
            stocks = []
            for country in countries:
                country_stocks = REGIONAL_STOCKS.get(country, [])
                for stock in country_stocks:
                    price_data = await self._get_stock_price(stock["symbol"], db)
                    stocks.append({
                        **stock,
                        "country": country,
                        "region": region,
                        **price_data
                    })
            result[region] = stocks

        return result

    async def _get_stock_price(self, symbol: str, db: AsyncSession) -> dict[str, Any]:
        price = MOCK_PRICES.get(symbol, 100.00)
        change = price * 0.01 * (1 if symbol[0].isalpha() and len(symbol) < 5 else -1)

        return {
            "current_price": price,
            "change": round(change, 2),
            "change_percent": round((change / price) * 100, 2),
            "previous_close": price - change,
            "last_updated": datetime.utcnow().isoformat()
        }

    async def initialize_stocks_db(self, db: AsyncSession) -> dict[str, Any]:
        created = 0
        updated = 0

        for country, stocks in REGIONAL_STOCKS.items():
            region_map = {
                "US": "North America", "MX": "North America",
                "BR": "South America", "CO": "South America", "CL": "South America",
                "GB": "Europe", "DE": "Europe", "FR": "Europe",
                "JP": "Asia", "CN": "Asia"
            }
            region = region_map.get(country, "Other")

            for stock in stocks:
                stmt = select(InternationalStock).where(InternationalStock.symbol == stock["symbol"])
                result = await db.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    existing.name = stock["name"]
                    existing.exchange = stock["exchange"]
                    existing.sector = stock["sector"]
                    existing.currency = stock["currency"]
                    updated += 1
                else:
                    new_stock = InternationalStock(
                        symbol=stock["symbol"],
                        name=stock["name"],
                        exchange=stock["exchange"],
                        country=country,
                        region=region,
                        sector=stock["sector"],
                        currency=stock["currency"]
                    )
                    db.add(new_stock)
                    created += 1

        await db.flush()
        return {"created": created, "updated": updated}


async def preload_international_stocks(db: AsyncSession):
    async with InternationalStocksService() as service:
        return await service.initialize_stocks_db(db)
