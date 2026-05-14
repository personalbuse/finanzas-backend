from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date


class StockInfo(BaseModel):
    symbol: str
    price: float
    change: float
    change_percent: str
    volume: int
    last_trading_day: str
    previous_close: float
    source: str
    timestamp: str


class HistoricalData(BaseModel):
    symbol: str
    prices: list
    source: str


class HistoryItem(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class WorldIndexResponse(BaseModel):
    symbol: str
    name: str
    country: str
    region: str
    currency: str
    current_value: Optional[float] = None
    change: Optional[float] = None
    change_percent: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    previous_close: Optional[float] = None
    last_updated: Optional[str] = None


class IndexHistoryResponse(BaseModel):
    index_symbol: str
    date: date
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None


class InternationalStockResponse(BaseModel):
    id: int
    symbol: str
    name: str
    exchange: str
    country: str
    region: str
    sector: Optional[str] = None
    currency: str
    current_price: Optional[float] = None
    change: Optional[float] = None
    change_percent: Optional[float] = None
    previous_close: Optional[float] = None
    last_updated: Optional[str] = None
    is_active: bool


class InternationalStockCreate(BaseModel):
    symbol: str
    name: str
    exchange: str
    country: str
    region: str
    sector: Optional[str] = None
    currency: str


class BatchStocksRequest(BaseModel):
    symbols: List[str] = Field(..., max_items=100)
    cache_ttl: int = Field(default=86400)
