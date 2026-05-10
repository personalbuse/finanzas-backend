from sqlalchemy import Column, Integer, String, DateTime, Numeric, Boolean, ForeignKey, func, PrimaryKeyConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    initial_balance = Column(Numeric(15, 2), default=10000.00)
    current_balance = Column(Numeric(15, 2), default=10000.00)
    is_active = Column(Boolean, default=True)
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
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    symbol = Column(String(10), nullable=False)
    transaction_type = Column(String(10), nullable=False)  # 'buy' o 'sell'
    quantity = Column(Numeric(15, 4), nullable=False)
    price_per_unit = Column(Numeric(15, 4), nullable=False)
    total_amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(3), default="USD")
    created_at = Column(DateTime, default=func.now())
    
    user = relationship("User", back_populates="transactions")


class CacheData(Base):
    __tablename__ = "cache_data"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(255), unique=True, index=True, nullable=False)
    value = Column(String(1000), nullable=False)
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
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    code = Column(String(6), nullable=False)
    code_type = Column(String(20), nullable=False)  # '2fa', 'email_verification'
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    attempts = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    
    user = relationship("User")
