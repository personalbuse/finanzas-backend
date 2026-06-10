
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.news_service import NewsService

router = APIRouter()


@router.get("")
async def get_news(
    category: str | None = Query(None, description="Category: general, forex, crypto, merger"),
    limit: int = Query(3, ge=1, le=10),
    db: AsyncSession = Depends(get_db)
):
    async with NewsService() as service:
        news = await service.get_news(category=category, limit=limit, db=db)
        return {"news": news, "total": len(news)}


@router.get("/symbol/{symbol}")
async def get_news_by_symbol(
    symbol: str,
    limit: int = Query(3, ge=1, le=10)
):
    async with NewsService() as service:
        news = await service.get_news_by_symbol(symbol=symbol.upper(), limit=limit)
        return {"symbol": symbol.upper(), "news": news, "total": len(news)}
