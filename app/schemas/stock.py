from datetime import date

from pydantic import BaseModel, Field


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
    current_value: float | None = None
    change: float | None = None
    change_percent: float | None = None
    high: float | None = None
    low: float | None = None
    previous_close: float | None = None
    last_updated: str | None = None


class IndexHistoryResponse(BaseModel):
    index_symbol: str
    date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: int | None = None


class InternationalStockResponse(BaseModel):
    id: int
    symbol: str
    name: str
    exchange: str
    country: str
    region: str
    sector: str | None = None
    currency: str
    current_price: float | None = None
    change: float | None = None
    change_percent: float | None = None
    previous_close: float | None = None
    last_updated: str | None = None
    is_active: bool


class InternationalStockCreate(BaseModel):
    symbol: str
    name: str
    exchange: str
    country: str
    region: str
    sector: str | None = None
    currency: str


class BatchStocksRequest(BaseModel):
    symbols: list[str] = Field(..., max_items=100)
    cache_ttl: int = Field(default=86400)
