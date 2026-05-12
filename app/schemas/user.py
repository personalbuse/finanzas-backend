import re
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime


def validate_password_strength(password: str) -> str:
    errors = []
    if len(password) < 12:
        errors.append('12 caracteres')
    if not re.search(r'[A-Z]', password):
        errors.append('una mayúscula')
    if not re.search(r'[a-z]', password):
        errors.append('una minúscula')
    if not re.search(r'\d', password):
        errors.append('un número')
    if not re.search(r'[@$!%*?&]', password):
        errors.append('un símbolo')

    if errors:
        raise ValueError(f'La contraseña debe tener: {", ".join(errors)}')
    return password


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    password: str = Field(..., min_length=12, max_length=100)
    initial_balance: Optional[float] = Field(default=10000.00, ge=1000)

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        return validate_password_strength(v)


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    initial_balance: float
    current_balance: float
    completed_courses: int = 0
    rol: str = "inversor"
    created_at: datetime
    
    class Config:
        from_attributes = True


class CourseProgressResponse(BaseModel):
    completed_courses: int
    bonus_earned: int


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    username: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class BuyRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=10, pattern=r'^[A-Za-z][A-Za-z0-9.\-]{0,9}$')
    quantity: float = Field(..., gt=0, le=1_000_000)
    currency: str = Field(default="USD")


class SellRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=10, pattern=r'^[A-Za-z][A-Za-z0-9.\-]{0,9}$')
    quantity: float = Field(..., gt=0, le=1_000_000)


class PortfolioItem(BaseModel):
    symbol: str
    quantity: float
    average_cost: float
    current_price: Optional[float] = None
    stock_value: Optional[float] = None
    stock_profit: Optional[float] = None
    stock_profit_percent: Optional[float] = None


class PortfolioResponse(BaseModel):
    total_cost: float
    total_value: float
    total_profit: float
    total_profit_percent: float
    stocks: list


class TransactionItem(BaseModel):
    id: int
    symbol: str
    transaction_type: str
    quantity: float
    price_per_unit: float
    total_amount: float
    currency: str
    created_at: datetime


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


class ExchangeRateResponse(BaseModel):
    from_currency: str
    to_currency: str
    rate: float
    timestamp: str
    source: str


class ConvertCurrencyResponse(BaseModel):
    amount: float
    from_currency: str
    converted_amount: float
    to_currency: str
    rate: float
    timestamp: str


class ErrorDetail(BaseModel):
    detail: str
