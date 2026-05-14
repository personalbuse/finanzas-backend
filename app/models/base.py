from sqlalchemy import Column, Integer, String, DateTime, Date, Numeric, Boolean, ForeignKey, func, PrimaryKeyConstraint, UniqueConstraint, Index, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime, date

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    initial_balance = Column(Numeric(15, 2), default=10000.00)
    current_balance = Column(Numeric(15, 2), default=10000.00)
    completed_courses = Column(Integer, default=0)
    rol = Column(String(20), default="inversor", index=True)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    portfolios = relationship("Portfolio", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")


class Portfolio(Base):
    __tablename__ = "portfolios"
    
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    symbol = Column(String(10), nullable=False)
    quantity = Column(Numeric(15, 4), nullable=False)
    average_cost = Column(Numeric(15, 4), nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    user = relationship("User", back_populates="portfolios")
    
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "symbol"),
    )


class Transaction(Base):
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    symbol = Column(String(10), nullable=False)
    transaction_type = Column(String(10), nullable=False)
    quantity = Column(Numeric(15, 4), nullable=False)
    price_per_unit = Column(Numeric(15, 4), nullable=False)
    total_amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(3), default="USD")
    created_at = Column(DateTime, default=func.now(), index=True)
    
    user = relationship("User", back_populates="transactions")


class CacheData(Base):
    __tablename__ = "cache_data"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(255), unique=True, index=True, nullable=False)
    value = Column(Text, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=func.now())
    
    @classmethod
    def generate_key(cls, *parts):
        return ":".join(parts)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(255), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    
    user = relationship("User")


class VerificationCode(Base):
    __tablename__ = "verification_codes"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(6), nullable=False)
    code_type = Column(String(20), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False, index=True)
    attempts = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    
    user = relationship("User")


class ExchangeRateHistory(Base):
    __tablename__ = "exchange_rate_history"
    
    id = Column(Integer, primary_key=True, index=True)
    from_currency = Column(String(3), nullable=False)
    to_currency = Column(String(3), nullable=False)
    rate = Column(Numeric(15, 6), nullable=False)
    date = Column(Date, nullable=False)
    created_at = Column(DateTime, default=func.now())
    
    __table_args__ = (
        UniqueConstraint('from_currency', 'to_currency', 'date', name='unique_rate_date'),
        Index('idx_rate_currencies_date', 'from_currency', 'to_currency', 'date'),
    )


class WorldIndex(Base):
    __tablename__ = "world_indices"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(30), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    country = Column(String(3), nullable=False, index=True)
    region = Column(String(50), nullable=False, index=True)
    currency = Column(String(3), nullable=False)
    current_value = Column(Numeric(15, 2), nullable=True)
    change = Column(Numeric(15, 4), nullable=True)
    change_percent = Column(Numeric(15, 4), nullable=True)
    high = Column(Numeric(15, 2), nullable=True)
    low = Column(Numeric(15, 2), nullable=True)
    previous_close = Column(Numeric(15, 2), nullable=True)
    last_updated = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class IndexHistory(Base):
    __tablename__ = "index_history"

    id = Column(Integer, primary_key=True, index=True)
    index_symbol = Column(String(30), ForeignKey("world_indices.symbol", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(Date, nullable=False)
    open = Column(Numeric(15, 2), nullable=True)
    high = Column(Numeric(15, 2), nullable=True)
    low = Column(Numeric(15, 2), nullable=True)
    close = Column(Numeric(15, 2), nullable=True)
    volume = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=func.now())
    
    __table_args__ = (
        UniqueConstraint('index_symbol', 'date', name='unique_index_date'),
        Index('idx_index_date', 'index_symbol', 'date'),
    )


class InternationalStock(Base):
    __tablename__ = "international_stocks"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(150), nullable=False)
    exchange = Column(String(50), nullable=False)
    country = Column(String(3), nullable=False, index=True)
    region = Column(String(30), nullable=False, index=True)
    sector = Column(String(50), nullable=True)
    currency = Column(String(3), nullable=False)
    current_price = Column(Numeric(15, 4), nullable=True)
    change = Column(Numeric(15, 4), nullable=True)
    change_percent = Column(Numeric(15, 4), nullable=True)
    previous_close = Column(Numeric(15, 4), nullable=True)
    last_updated = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
