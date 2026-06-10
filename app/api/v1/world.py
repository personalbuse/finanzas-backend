
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CustomException
from app.core.rate_limiter import limiter, stocks_rate_limit
from app.core.security import require_admin_api_key
from app.db.session import get_db
from app.services.international_stocks_service import (
    InternationalStocksService,
    preload_international_stocks,
)
from app.services.world_indices_service import WorldIndicesService, preload_world_indices

router = APIRouter()


@router.get("/indices")
@limiter.limit(stocks_rate_limit)
async def get_world_indices(
    request: Request,
    db: AsyncSession = Depends(get_db),
    region: str | None = Query(None, description="Filter by region: North America, South America, Europe, Asia, Oceania, Global")
):
    async with WorldIndicesService() as service:
        if region:
            indices = await service.get_indices_by_region(region, db)
            return {"region": region, "indices": indices}
        indices = await service.get_indices(db)
        return {"indices": indices, "total": len(indices)}


@router.get("/indices/{symbol}")
@limiter.limit(stocks_rate_limit)
async def get_index_by_symbol(
    request: Request,
    symbol: str,
    db: AsyncSession = Depends(get_db)
):
    async with WorldIndicesService() as service:
        index = await service.get_index_by_symbol(symbol.upper(), db)
        if not index:
            raise CustomException(status_code=404, detail=f"Index {symbol} not found")
        return index


@router.post("/indices/preload")
async def preload_indices(
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(require_admin_api_key)
):
    result = await preload_world_indices(db)
    return {"message": "World indices preloaded", "result": result}


@router.get("/stocks/international")
@limiter.limit(stocks_rate_limit)
async def get_international_stocks(
    request: Request,
    db: AsyncSession = Depends(get_db),
    region: str | None = Query(None, description="Filter by region")
):
    async with InternationalStocksService() as service:
        if region:
            stocks = await service.get_stocks_by_region(region, db)
            return {"region": region, "stocks": stocks, "total": len(stocks)}
        all_stocks = await service.get_all_regions(db)

        flat_stocks = []
        for region_stocks in all_stocks.values():
            flat_stocks.extend(region_stocks)

        return {"stocks": flat_stocks, "total": len(flat_stocks), "by_region": all_stocks}


@router.get("/stocks/international/{country}")
@limiter.limit(stocks_rate_limit)
async def get_stocks_by_country(
    request: Request,
    country: str,
    db: AsyncSession = Depends(get_db)
):
    from app.services.international_stocks_service import REGIONAL_STOCKS

    stocks = REGIONAL_STOCKS.get(country.upper(), [])
    if not stocks:
        raise CustomException(status_code=404, detail=f"Country {country} not found")

    async with InternationalStocksService() as service:
        result = []
        for stock in stocks:
            price_data = await service._get_stock_price(stock["symbol"], db)
            result.append({
                **stock,
                **price_data
            })

    return {"country": country.upper(), "stocks": result}


@router.post("/stocks/international/preload")
async def preload_int_stocks(
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(require_admin_api_key)
):
    result = await preload_international_stocks(db)
    return {"message": "International stocks preloaded", "result": result}


@router.get("/markets/regions")
@limiter.limit(stocks_rate_limit)
async def get_regions(
    request: Request,
):
    return {
        "regions": [
            {"id": "north_america", "name": "North America", "countries": ["US", "MX"]},
            {"id": "south_america", "name": "South America", "countries": ["BR", "CO", "CL", "PE", "AR"]},
            {"id": "europe", "name": "Europe", "countries": ["GB", "DE", "FR", "ES", "IT"]},
            {"id": "asia", "name": "Asia", "countries": ["JP", "CN", "HK", "IN", "KR"]},
            {"id": "oceania", "name": "Oceania", "countries": ["AU", "NZ"]}
        ]
    }
