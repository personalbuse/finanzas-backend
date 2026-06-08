import jwt
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ForbiddenException
from app.core.rate_limiter import limiter, portfolio_rate_limit
from app.db.session import get_db
from app.models.base import User
from app.services.auth_service import get_current_user, get_token_from_request
from app.services.finnhub_service import FinnhubService
from app.repositories.portfolio_repository import (
    add_stock_to_portfolio,
    remove_stock_from_portfolio,
    get_transaction_history,
    create_transaction,
    calculate_portfolio_values,
    get_portfolio_by_symbol,
)
from app.schemas.user import BuyRequest, SellRequest
from app.schemas.portfolio import PortfolioResponse, TransactionHistory

logger = logging.getLogger(__name__)
router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/login", auto_error=False)


async def get_authenticated_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
) -> User:
    if not token:
        token = get_token_from_request(request)
    return await get_current_user(db, token)


async def get_current_username(
    request: Request,
    token: str = Depends(oauth2_scheme),
) -> str:
    if not token:
        token = get_token_from_request(request)
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales inválidas",
            )
        return username
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
        )


def ensure_own_resource(path_user_id: int, current_user: User) -> None:
    if path_user_id != current_user.id:
        raise ForbiddenException("No puedes acceder a recursos de otro usuario")


@router.get(
    "/portfolio",
    response_model=PortfolioResponse,
    tags=["portafolio"],
)
@router.get(
    "/portfolio/values",
    response_model=PortfolioResponse,
    tags=["portafolio"],
)
@limiter.limit(portfolio_rate_limit)
async def get_my_portfolio_values(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_authenticated_user),
):
    try:
        return await calculate_portfolio_values(db, current_user.id)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error al obtener valores del portafolio")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener valores del portafolio",
        )


@router.get(
    "/portfolio/values/{user_id}",
    response_model=PortfolioResponse,
    tags=["portafolio"],
)
@limiter.limit(portfolio_rate_limit)
async def get_portfolio_values_legacy(
    request: Request,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_authenticated_user),
):
    ensure_own_resource(user_id, current_user)
    return await get_my_portfolio_values(request, db, current_user)


@router.post(
    "/portfolio/buy",
    tags=["portafolio"],
)
@limiter.limit(portfolio_rate_limit)
async def buy_stock(
    request: Request,
    buy_data: BuyRequest,
    db: AsyncSession = Depends(get_db),
    current_username: str = Depends(get_current_username),
):
    symbol = buy_data.symbol.upper()

    try:
        async with FinnhubService() as service:
            stock_data = await service.get_stock_price(symbol, db)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo obtener el precio de la acción",
        )

    if db.in_transaction():
        await db.rollback()

    price_per_unit = float(stock_data["price"])
    total_cost = float(buy_data.quantity) * price_per_unit

    try:
        async with db.begin():
            result = await db.execute(
                select(User)
                .where(User.username == current_username)
                .with_for_update()
            )
            user = result.scalar_one_or_none()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Usuario no encontrado",
                )
            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Usuario inactivo",
                )

            current_balance = float(user.current_balance)
            if total_cost > current_balance:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Saldo insuficiente para realizar esta compra",
                )

            user.current_balance = current_balance - total_cost
            await add_stock_to_portfolio(db, user.id, symbol, buy_data.quantity, price_per_unit)
            await create_transaction(
                db,
                user.id,
                symbol,
                "buy",
                buy_data.quantity,
                price_per_unit,
                total_cost,
            )

        return {
            "message": "Compra realizada exitosamente",
            "stock": symbol,
            "quantity": buy_data.quantity,
            "price_per_unit": price_per_unit,
            "total_cost": round(total_cost, 2),
            "remaining_balance": round(current_balance - total_cost, 2),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error al realizar compra")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al realizar compra",
        )


@router.post(
    "/portfolio/sell",
    tags=["portafolio"],
)
@limiter.limit(portfolio_rate_limit)
async def sell_stock(
    request: Request,
    sell_data: SellRequest,
    db: AsyncSession = Depends(get_db),
    current_username: str = Depends(get_current_username),
):
    symbol = sell_data.symbol.upper()

    try:
        async with FinnhubService() as service:
            stock_data = await service.get_stock_price(symbol, db)
    except Exception as e:
        logger.exception("Error obteniendo precio de acción para venta")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo obtener el precio de la acción",
        )

    if db.in_transaction():
        await db.rollback()

    price_per_unit = float(stock_data["price"])
    total_gain = float(sell_data.quantity) * price_per_unit

    try:
        async with db.begin():
            result = await db.execute(
                select(User)
                .where(User.username == current_username)
                .with_for_update()
            )
            user = result.scalar_one_or_none()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Usuario no encontrado",
                )
            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Usuario inactivo",
                )

            portfolio = await get_portfolio_by_symbol(db, user.id, symbol)
            if not portfolio:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No tienes suficientes acciones de esta empresa para vender",
                )

            if float(portfolio.quantity) < float(sell_data.quantity):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cantidad insuficiente para vender",
                )

            await remove_stock_from_portfolio(db, user.id, symbol, sell_data.quantity)
            user.current_balance = float(user.current_balance) + total_gain
            await create_transaction(
                db,
                user.id,
                symbol,
                "sell",
                sell_data.quantity,
                price_per_unit,
                total_gain,
            )

            remaining_balance = float(user.current_balance)

        return {
            "message": "Venta realizada exitosamente",
            "stock": symbol,
            "quantity": sell_data.quantity,
            "price_per_unit": price_per_unit,
            "total_gain": round(total_gain, 2),
            "remaining_balance": round(remaining_balance, 2),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error al realizar venta")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al realizar venta",
        )


@router.get(
    "/portfolio/history",
    response_model=TransactionHistory,
    tags=["portafolio"],
)
@limiter.limit(portfolio_rate_limit)
async def get_my_transaction_history(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_authenticated_user),
    skip: int = 0,
    limit: int = 100,
):
    try:
        safe_limit = max(1, min(limit, 100))
        safe_skip = max(0, skip)
        transactions = await get_transaction_history(db, current_user.id, safe_skip, safe_limit)
        return {"transactions": transactions, "total_count": len(transactions)}
    except Exception as e:
        logger.exception("Error al obtener historial")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener historial",
        )


@router.get(
    "/portfolio/history/{user_id}",
    response_model=TransactionHistory,
    tags=["portafolio"],
)
@limiter.limit(portfolio_rate_limit)
async def get_transaction_history_legacy(
    request: Request,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_authenticated_user),
    skip: int = 0,
    limit: int = 100,
):
    ensure_own_resource(user_id, current_user)
    return await get_my_transaction_history(request, db, current_user, skip, limit)


@router.get(
    "/portfolio/report",
    tags=["portafolio"],
)
@limiter.limit(portfolio_rate_limit)
async def get_portfolio_report(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_authenticated_user),
):
    try:
        from app.services.pdf_report_service import generate_report

        pdf_bytes = await generate_report(db, current_user.id)

        from fastapi.responses import Response
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=portafolio_{current_user.username}_{datetime.now().strftime('%Y%m%d')}.pdf"
            }
        )
    except Exception as e:
        logger.exception("Error generando PDF")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al generar el reporte PDF"
        )
