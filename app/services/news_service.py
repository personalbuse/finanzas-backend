from datetime import datetime
from typing import Dict, Any, List, Optional
import logging
import httpx

from app.core.api_keys import ApiKeys
from app.services.cache_service import CacheService

logger = logging.getLogger(__name__)


MOCK_NEWS = [
    {
        "id": "1",
        "headline": "Fed signals potential rate cut in upcoming meetings",
        "summary": "The Federal Reserve indicated it may consider reducing interest rates in the next several meetings as inflation continues to moderate toward its 2% target.",
        "url": "https://example.com/news/1",
        "image": "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=400&h=200&fit=crop",
        "source": "Reuters",
        "datetime": datetime.utcnow().isoformat(),
        "category": "economy"
    },
    {
        "id": "2",
        "headline": "Global markets rally on positive economic data",
        "summary": "Stock markets around the world posted gains as better-than-expected economic data from major economies fueled optimism about the global economic outlook.",
        "url": "https://example.com/news/2",
        "image": "https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f?w=400&h=200&fit=crop",
        "source": "Bloomberg",
        "datetime": datetime.utcnow().isoformat(),
        "category": "market"
    },
    {
        "id": "3",
        "headline": "Colombian peso strengthens against the dollar",
        "summary": "The Colombian peso appreciated against the US dollar as investors digested the latest central bank decisions and commodity price movements.",
        "url": "https://example.com/news/3",
        "image": "https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?w=400&h=200&fit=crop",
        "source": "El Tiempo",
        "datetime": datetime.utcnow().isoformat(),
        "category": "forex"
    }
]


class NewsService:
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

    async def get_news(self, category: Optional[str] = None, limit: int = 3, db=None) -> List[Dict[str, Any]]:
        cache_key = f"{category or 'general'}:{limit}"
        
        if db:
            cached = await CacheService.get(db, "news", cache_key)
            if cached:
                return cached
        
        if not self.api_key:
            logger.warning("No Finnhub API key, using mock news")
            return MOCK_NEWS[:limit]

        try:
            url = f"{self.BASE_URL}/news"
            params = {
                "token": self.api_key,
                "category": category or "general",
            }

            response = await self.http_client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            news_items = []
            for item in data[:limit]:
                news_items.append({
                    "id": str(item.get("id", "")),
                    "headline": item.get("headline", ""),
                    "summary": item.get("summary", "")[:200] + "..." if item.get("summary") else "",
                    "url": item.get("url", ""),
                    "image": item.get("image", ""),
                    "source": item.get("source", "Unknown"),
                    "datetime": datetime.fromtimestamp(item.get("datetime", 0)).isoformat() if item.get("datetime") else datetime.utcnow().isoformat(),
                    "category": item.get("category", "general")
                })

            result = news_items if news_items else MOCK_NEWS[:limit]
            
            if db:
                await CacheService.set(db, "news", cache_key, value=result, ttl_seconds=1800)
            
            return result

        except Exception as e:
            logger.error(f"Error fetching news: {e}")
            return MOCK_NEWS[:limit]

    async def get_news_by_symbol(self, symbol: str, limit: int = 3) -> List[Dict[str, Any]]:
        if not self.api_key:
            return MOCK_NEWS[:limit]

        try:
            url = f"{self.BASE_URL}/company-news"
            params = {
                "symbol": symbol.upper(),
                "from": (datetime.utcnow().replace(hour=0, minute=0, second=0)).strftime("%Y-%m-%d"),
                "to": datetime.utcnow().strftime("%Y-%m-%d"),
                "token": self.api_key
            }

            response = await self.http_client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if not data or data == "No symbol found":
                return MOCK_NEWS[:limit]

            news_items = []
            for item in data[:limit]:
                news_items.append({
                    "id": str(item.get("id", "")),
                    "headline": item.get("headline", ""),
                    "summary": item.get("summary", "")[:200] + "..." if item.get("summary") else "",
                    "url": item.get("url", ""),
                    "image": item.get("image", ""),
                    "source": item.get("source", "Unknown"),
                    "datetime": datetime.fromtimestamp(item.get("datetime", 0)).isoformat() if item.get("datetime") else datetime.utcnow().isoformat(),
                    "category": "company"
                })

            return news_items if news_items else MOCK_NEWS[:limit]

        except Exception as e:
            logger.error(f"Error fetching news for {symbol}: {e}")
            return MOCK_NEWS[:limit]