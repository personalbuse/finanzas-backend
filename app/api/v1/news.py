from fastapi import APIRouter, Query
from typing import Optional

from app.services.news_service import NewsService

router = APIRouter()


@router.get("")
async def get_news(
    category: Optional[str] = Query(None, description="Category: general, forex, crypto, merger"),
    limit: int = Query(3, ge=1, le=10)
):
    async with NewsService() as service:
        news = await service.get_news(category=category, limit=limit)
        return {"news": news, "total": len(news)}


@router.get("/symbol/{symbol}")
async def get_news_by_symbol(
    symbol: str,
    limit: int = Query(3, ge=1, le=10)
):
    async with NewsService() as service:
        news = await service.get_news_by_symbol(symbol=symbol.upper(), limit=limit)
        return {"symbol": symbol.upper(), "news": news, "total": len(news)}