import re
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

USERNAME_PATTERN = r'^[a-z0-9_.-]{3,50}$'


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


def normalize_username(v: str) -> str:
    lower = v.lower().strip()
    if not re.match(USERNAME_PATTERN, lower):
        raise ValueError(
            'El nombre de usuario solo puede contener letras minúsculas, '
            'números, puntos, guiones y guiones bajos (3-50 caracteres)'
        )
    return lower


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=12, max_length=100)
    initial_balance: float | None = Field(default=10000.00, ge=1000)

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        return normalize_username(v)

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        return validate_password_strength(v)


class UserUpdate(BaseModel):
    username: str | None = Field(None, min_length=3, max_length=50)
    email: EmailStr | None = None
    current_password: str | None = Field(None, min_length=1)
    new_password: str | None = Field(None, min_length=12, max_length=100)

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        if v is not None:
            return normalize_username(v)
        return v

    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if v:
            return validate_password_strength(v)
        return v


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
    username: str | None = None


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
    current_price: float | None = None
    stock_value: float | None = None
    stock_profit: float | None = None
    stock_profit_percent: float | None = None


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


class TOTPSetupResponse(BaseModel):
    secret: str
    qr_code: str
    provisioning_uri: str

class TOTPVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)

class TOTPVerifyResponse(BaseModel):
    enabled: bool
    backup_codes: list[str]

class TOTPStatusResponse(BaseModel):
    enabled: bool
    setup_at: datetime | None = None

class TOTPDisableRequest(BaseModel):
    password: str = Field(..., min_length=1)
    code: str = Field(..., min_length=6, max_length=20)

class TOTPLoginVerifyRequest(BaseModel):
    temp_token: str = Field(..., min_length=1)
    code: str = Field(..., min_length=1, max_length=12)

class TOTPBackupCodeRequest(BaseModel):
    temp_token: str = Field(..., min_length=1)
    backup_code: str = Field(..., min_length=1, max_length=20)

class ErrorDetail(BaseModel):
    detail: str
