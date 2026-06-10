from datetime import datetime

from pydantic import BaseModel


class PortfolioItem(BaseModel):
    symbol: str
    quantity: float
    average_cost: float
    current_price: float
    stock_value: float
    stock_profit: float
    stock_profit_percent: float


class PortfolioResponse(BaseModel):
    total_cost: float
    total_value: float
    total_profit: float
    total_profit_percent: float
    stocks: list[PortfolioItem]


class TransactionItem(BaseModel):
    id: int
    symbol: str
    transaction_type: str
    quantity: float
    price_per_unit: float
    total_amount: float
    currency: str
    created_at: datetime


class TransactionHistory(BaseModel):
    transactions: list[TransactionItem]
    total_count: int
