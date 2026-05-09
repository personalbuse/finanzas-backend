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
