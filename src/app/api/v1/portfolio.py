from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limiter import limiter, portfolio_rate_limit
from app.db.session import get_db
from app.services.finnhub_service import FinnhubService
from app.repositories.portfolio_repository import (
    get_portfolio_by_user,
    add_stock_to_portfolio,
    remove_stock_from_portfolio,
    get_transaction_history,
    create_transaction,
    calculate_portfolio_values
)
from app.repositories.user_repository import get_user_by_id, update_user_balance
from app.schemas.user import BuyRequest, SellRequest
from app.schemas.portfolio import PortfolioResponse, TransactionHistory

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/login")


@router.get(
    "/portfolio/{user_id}",
    response_model=PortfolioResponse,
    tags=["portafolio"]
)
@limiter.limit(portfolio_rate_limit)
async def get_portfolio(
    request: Request,
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    try:
        portfolio_data = await calculate_portfolio_values(db, user_id)
        return portfolio_data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener portafolio: {str(e)}"
        )


@router.post(
    "/portfolio/buy",
    tags=["portafolio"]
)
@limiter.limit(portfolio_rate_limit)
async def buy_stock(
    request: Request,
    buy_data: BuyRequest,
    db: AsyncSession = Depends(get_db)
):
    try:
        user = await get_user_by_id(db, buy_data.user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Usuario no encontrado"
            )
        
        async with FinnhubService() as service:
            stock_data = await service.get_stock_price(buy_data.symbol, db)
        
        price_per_unit = stock_data["price"]
        total_cost = buy_data.quantity * price_per_unit
        
        current_balance = float(user.current_balance)
        if total_cost > current_balance:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Saldo insuficiente para realizar esta compra"
            )
        
        await update_user_balance(db, buy_data.user_id, -total_cost)
        await add_stock_to_portfolio(db, buy_data.user_id, buy_data.symbol, buy_data.quantity, price_per_unit)
        await create_transaction(
            db, buy_data.user_id, buy_data.symbol, "buy", 
            buy_data.quantity, price_per_unit, total_cost
        )
        
        return {
            "message": "Compra realizada exitosamente",
            "stock": buy_data.symbol,
            "quantity": buy_data.quantity,
            "price_per_unit": price_per_unit,
            "total_cost": total_cost,
            "remaining_balance": current_balance - total_cost
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al realizar compra: {str(e)}"
        )


@router.post(
    "/portfolio/sell",
    tags=["portafolio"]
)
@limiter.limit(portfolio_rate_limit)
async def sell_stock(
    request: Request,
    sell_data: SellRequest,
    db: AsyncSession = Depends(get_db)
):
    try:
        async with FinnhubService() as service:
            stock_data = await service.get_stock_price(sell_data.symbol, db)
        
        price_per_unit = stock_data["price"]
        total_gain = sell_data.quantity * price_per_unit
        
        from app.repositories.portfolio_repository import get_portfolio_by_symbol
        portfolio = await get_portfolio_by_symbol(db, sell_data.user_id, sell_data.symbol)
        
        if not portfolio:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No tienes suficientes acciones de esta empresa para vender"
            )
        
        if float(portfolio.quantity) < float(sell_data.quantity):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cantidad insuficiente para vender"
            )
        
        await remove_stock_from_portfolio(db, sell_data.user_id, sell_data.symbol, sell_data.quantity)
        await update_user_balance(db, sell_data.user_id, total_gain)
        await create_transaction(
            db, sell_data.user_id, sell_data.symbol, "sell", 
            sell_data.quantity, price_per_unit, total_gain
        )
        
        user = await get_user_by_id(db, sell_data.user_id)
        
        return {
            "message": "Venta realizada exitosamente",
            "stock": sell_data.symbol,
            "quantity": sell_data.quantity,
            "price_per_unit": price_per_unit,
            "total_gain": total_gain,
            "remaining_balance": float(user.current_balance) if user else 0
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al realizar venta: {str(e)}"
        )


@router.get(
    "/portfolio/history/{user_id}",
    response_model=TransactionHistory,
    tags=["portafolio"]
)
@limiter.limit(portfolio_rate_limit)
async def get_transaction_history_endpoint(
    request: Request,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    try:
        transactions = await get_transaction_history(db, user_id, skip, limit)
        return {"transactions": transactions, "total_count": len(transactions)}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener historial: {str(e)}"
        )


@router.get(
    "/portfolio/values/{user_id}",
    response_model=PortfolioResponse,
    tags=["portafolio"]
)
@limiter.limit(portfolio_rate_limit)
async def get_portfolio_values(
    request: Request,
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    try:
        portfolio_data = await calculate_portfolio_values(db, user_id)
        return portfolio_data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener valores del portafolio: {str(e)}"
        )