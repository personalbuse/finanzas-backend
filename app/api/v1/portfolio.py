import logging
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenException
from app.core.rate_limiter import limiter, portfolio_rate_limit
from app.db.session import get_db
from app.models.base import User
from app.repositories.portfolio_repository import (
    add_stock_to_portfolio,
    calculate_portfolio_values,
    create_transaction,
    get_portfolio_by_symbol,
    get_transaction_history,
    remove_stock_from_portfolio,
)
from app.schemas.portfolio import PortfolioResponse, TransactionHistory
from app.schemas.user import BuyRequest, SellRequest
from app.services.auth_service import get_current_user, get_token_from_request
from app.services.finnhub_service import FinnhubService

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
    except Exception:
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
    current_user: User = Depends(get_authenticated_user),
):
    current_user_id = current_user.id
    symbol = buy_data.symbol.upper()
    logger.info("=== DEBUG buy_stock start ===")
    logger.info(f"current_user type: {type(current_user).__name__}, id: {current_user_id}")
    logger.info(f"symbol={symbol}, quantity={buy_data.quantity}")
    logger.info(f"DB session id: {id(db)}, in_transaction: {db.in_transaction()}")

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
    logger.info(f"price_per_unit={price_per_unit}, total_cost={total_cost}")
    logger.info(f"DB in_transaction before begin(): {db.in_transaction()}")

    logger.info(f"About to enter db.begin(). Session state: in_transaction={db.in_transaction()}, is_active={db.is_active if hasattr(db, 'is_active') else 'N/A'}")

    try:
        async with db.begin():
            result = await db.execute(
                select(User)
                .where(User.id == current_user_id)
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
        logger.exception(f"=== DEBUG buy_stock EXCEPTION === type={type(e).__name__}, msg={str(e)}")
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
    current_user: User = Depends(get_authenticated_user),
):
    current_user_id = current_user.id
    symbol = sell_data.symbol.upper()

    logger.info("=== DEBUG sell_stock start ===")
    logger.info(f"current_user type: {type(current_user).__name__}, id: {current_user_id}")
    logger.info(f"symbol={symbol}, quantity={sell_data.quantity}")
    logger.info(f"DB session id: {id(db)}, in_transaction: {db.in_transaction()}")

    try:
        async with FinnhubService() as service:
            stock_data = await service.get_stock_price(symbol, db)
    except Exception:
        logger.exception("Error obteniendo precio de acción para venta")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo obtener el precio de la acción",
        )

    if db.in_transaction():
        await db.rollback()

    price_per_unit = float(stock_data["price"])
    total_gain = float(sell_data.quantity) * price_per_unit
    logger.info(f"price_per_unit={price_per_unit}, total_gain={total_gain}")
    logger.info(f"DB in_transaction before begin(): {db.in_transaction()}")

    logger.info(f"About to enter db.begin(). Session state: in_transaction={db.in_transaction()}, is_active={db.is_active if hasattr(db, 'is_active') else 'N/A'}")

    try:
        async with db.begin():
            result = await db.execute(
                select(User)
                .where(User.id == current_user_id)
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
        logger.exception(f"=== DEBUG sell_stock EXCEPTION === type={type(e).__name__}, msg={str(e)}")
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
    except Exception:
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

        pdf_bytes, sig_data = await generate_report(db, current_user.id)

        headers = {
            "Content-Disposition": f"attachment; filename=portafolio_{current_user.username}_{datetime.now().strftime('%Y%m%d')}.pdf"
        }
        if sig_data:
            headers["X-Signature"] = sig_data["signature_b64"]
            headers["X-Signature-Timestamp"] = sig_data["timestamp"]
            headers["X-Signature-Cert"] = sig_data["cert_serial"]

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers=headers,
        )
    except ValueError as e:
        logger.warning("Reporte PDF fallo: %s", e)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception:
        logger.exception("Error generando PDF")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al generar el reporte PDF"
        )


@router.post(
    "/portfolio/report/verify",
    tags=["portafolio"],
)
@limiter.limit("10/minute")
async def verify_pdf_signature(
    request: Request,
    file: UploadFile = File(...),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se aceptan archivos PDF",
        )

    try:
        content = await file.read()
        if len(content) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El archivo esta vacio",
            )

        from app.services.pdf_signature_service import PDFSignatureService
        sig_service = PDFSignatureService()

        sig_data = sig_service.extract_signature_from_pdf(content)
        if not sig_data:
            return {
                "valid": False,
                "message": "El PDF no contiene una firma digital valida de este sistema",
                "details": None,
            }

        meta_marker = b"\n% --- CERTIFICADO DE FIRMA DIGITAL ---"
        meta_start = content.find(meta_marker)
        if meta_start > 0:
            content_body = content[:meta_start]
        else:
            content_body = content

        result = sig_service.verify_pdf(content_body, sig_data["signature_b64"])

        return {
            "valid": result["valid"],
            "message": result["message"],
            "details": {
                "hash": result["hash_hex"],
                "cert_serial": result["cert_serial"],
                "cert_subject": result["cert_subject"],
                "signature_timestamp": sig_data["timestamp"],
            },
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error verificando firma PDF")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al verificar la firma del PDF",
        )
