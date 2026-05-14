from typing import Optional, List
import logging

from app.models.base import Portfolio, Transaction
from app.core.exceptions import CustomException, ValidationException
from app.services.finnhub_service import FinnhubService
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

logger = logging.getLogger(__name__)


async def get_portfolio_by_user(db: AsyncSession, user_id: int) -> List[Portfolio]:
    stmt = select(Portfolio).where(Portfolio.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_portfolio_by_symbol(db: AsyncSession, user_id: int, symbol: str) -> Optional[Portfolio]:
    stmt = select(Portfolio).where(
        and_(
            Portfolio.user_id == user_id,
            Portfolio.symbol == symbol.upper()
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def add_stock_to_portfolio(db: AsyncSession, user_id: int, symbol: str, 
                                quantity: float, price_per_unit: float) -> Portfolio:
    existing = await get_portfolio_by_symbol(db, user_id, symbol)
    
    if existing:
        old_quantity = float(existing.quantity)
        new_quantity = old_quantity + float(quantity)
        existing.average_cost = (
            (float(existing.average_cost) * old_quantity +
             float(price_per_unit) * float(quantity))
        ) / new_quantity
        existing.quantity = new_quantity
        await db.flush()
        return existing
    else:
        portfolio = Portfolio(
            user_id=user_id,
            symbol=symbol.upper(),
            quantity=quantity,
            average_cost=price_per_unit
        )
        db.add(portfolio)
        await db.flush()
        return portfolio


async def remove_stock_from_portfolio(db: AsyncSession, user_id: int, symbol: str, 
                                    quantity: float) -> bool:
    portfolio = await get_portfolio_by_symbol(db, user_id, symbol)
    
    if not portfolio:
        raise CustomException(status_code=404, detail="No se encontró la posición en el portafolio")
    
    if float(portfolio.quantity) < float(quantity):
        raise ValidationException(detail="Cantidad insuficiente para vender")
    
    portfolio.quantity = float(portfolio.quantity) - float(quantity)
    
    if float(portfolio.quantity) <= 0:
        await db.delete(portfolio)
    
    await db.flush()
    return True


async def get_transaction_history(db: AsyncSession, user_id: int, 
                                 skip: int = 0, limit: int = 100) -> List[Transaction]:
    stmt = select(Transaction).where(
        Transaction.user_id == user_id
    ).offset(skip).limit(limit).order_by(Transaction.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


async def create_transaction(db: AsyncSession, user_id: int, symbol: str, 
                            transaction_type: str, quantity: float, 
                            price_per_unit: float, total_amount: float,
                            currency: str = "USD") -> Transaction:
    transaction = Transaction(
        user_id=user_id,
        symbol=symbol.upper(),
        transaction_type=transaction_type,
        quantity=quantity,
        price_per_unit=price_per_unit,
        total_amount=total_amount,
        currency=currency.upper()
    )
    
    db.add(transaction)
    await db.flush()
    
    return transaction


async def get_current_stock_price(db: AsyncSession, symbol: str, service: FinnhubService) -> float:
    stock_data = await service.get_stock_price(symbol, db)
    return stock_data["price"]


async def calculate_portfolio_values(db: AsyncSession, user_id: int) -> dict:
    import asyncio
    portfolios = await get_portfolio_by_user(db, user_id)
    
    if not portfolios:
        return {
            "total_cost": 0,
            "total_value": 0,
            "total_profit": 0,
            "total_profit_percent": 0,
            "stocks": []
        }
    
    async with FinnhubService() as service:
        async def fetch_stock(portfolio):
            current_price = await get_current_stock_price(db, portfolio.symbol, service)
            return portfolio, current_price
        
        results = await asyncio.gather(
            *[fetch_stock(p) for p in portfolios],
            return_exceptions=True
        )
    
    total_cost = 0.0
    total_value = 0.0
    stocks = []
    
    for result in results:
        if isinstance(result, Exception):
            continue
        portfolio, current_price = result
        
        stock_value = float(portfolio.quantity) * current_price
        stock_cost = float(portfolio.quantity) * float(portfolio.average_cost)
        stock_profit = stock_value - stock_cost
        stock_profit_percent = (stock_profit / stock_cost * 100) if stock_cost > 0 else 0

        total_cost += stock_cost
        total_value += stock_value

        stocks.append({
            "symbol": portfolio.symbol,
            "quantity": float(portfolio.quantity),
            "average_cost": float(portfolio.average_cost),
            "current_price": current_price,
            "stock_value": round(stock_value, 2),
            "stock_cost": round(stock_cost, 2),
            "stock_profit": round(stock_profit, 2),
            "stock_profit_percent": round(stock_profit_percent, 2)
        })
    
    total_profit = total_value - total_cost
    total_profit_percent = (total_profit / total_cost * 100) if total_cost > 0 else 0
    
    return {
        "total_cost": round(total_cost, 2),
        "total_value": round(total_value, 2),
        "total_profit": round(total_profit, 2),
        "total_profit_percent": round(total_profit_percent, 2),
        "stocks": stocks
    }
