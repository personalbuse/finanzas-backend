import jwt
import logging
from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.rate_limiter import limiter, portfolio_rate_limit
from app.db.session import get_db
from app.models.base import User, Transaction
from app.repositories.portfolio_repository import calculate_portfolio_values
from app.schemas.user import UserResponse

logger = logging.getLogger(__name__)
router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/login")


class RoleRequest(BaseModel):
    new_role: str = Field(..., pattern="^(inversor|admin)$")


class BalanceRequest(BaseModel):
    new_balance: float = Field(..., ge=0)


async def require_admin(token: str = Depends(oauth2_scheme)) -> str:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("rol") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acceso solo para administradores",
            )
        return payload.get("sub")
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
        )


@router.get("/admin/users", tags=["admin"])
async def list_users(
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
    skip: int = 0,
    limit: int = 50,
):
    stmt = select(User).offset(skip).limit(limit).order_by(User.created_at.desc())
    result = await db.execute(stmt)
    users = result.scalars().all()
    return {
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "rol": u.rol,
                "is_active": u.is_active,
                "initial_balance": float(u.initial_balance),
                "current_balance": float(u.current_balance),
                "completed_courses": u.completed_courses or 0,
                "created_at": str(u.created_at),
            }
            for u in users
        ],
        "total": len(users),
    }


@router.get("/admin/users/{user_id}", tags=["admin"])
async def get_user_detail(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "rol": user.rol,
        "is_active": user.is_active,
        "initial_balance": float(user.initial_balance),
        "current_balance": float(user.current_balance),
        "completed_courses": user.completed_courses or 0,
        "created_at": str(user.created_at),
    }


@router.patch("/admin/users/{user_id}/role", tags=["admin"])
async def change_user_role(
    user_id: int,
    body: RoleRequest,
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    admin_result = await db.execute(select(User).where(User.username == admin))
    admin_user = admin_result.scalar_one_or_none()
    if admin_user and admin_user.id == user_id:
        raise HTTPException(status_code=403, detail="No puedes cambiar tu propio rol")
    user.rol = body.new_role
    await db.commit()
    return {"message": f"Rol cambiado a {body.new_role}", "user_id": user_id}


@router.patch("/admin/users/{user_id}/ban", tags=["admin"])
async def toggle_ban_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    admin_result = await db.execute(select(User).where(User.username == admin))
    admin_user = admin_result.scalar_one_or_none()
    if admin_user and admin_user.id == user_id:
        raise HTTPException(status_code=403, detail="No puedes banearte a ti mismo")
    user.is_active = not user.is_active
    await db.commit()
    status_text = "activado" if user.is_active else "baneado"
    return {"message": f"Usuario {status_text}", "user_id": user_id, "is_active": user.is_active}


@router.patch("/admin/users/{user_id}/balance", tags=["admin"])
async def adjust_balance(
    user_id: int,
    body: BalanceRequest,
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    user.current_balance = body.new_balance
    await db.commit()
    return {"message": "Saldo actualizado", "user_id": user_id, "new_balance": body.new_balance}


@router.get("/admin/kpis", tags=["admin"])
async def get_kpis(
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
):
    total_users = await db.scalar(select(func.count(User.id)))
    active_users = await db.scalar(select(func.count(User.id)).where(User.is_active == True))
    admin_count = await db.scalar(select(func.count(User.id)).where(User.rol == "admin"))
    total_transactions = await db.scalar(select(func.count(Transaction.id)))
    total_volume = await db.scalar(select(func.coalesce(func.sum(Transaction.total_amount), 0)))
    return {
        "total_users": total_users or 0,
        "active_users": active_users or 0,
        "admin_count": admin_count or 0,
        "total_transactions": total_transactions or 0,
        "total_volume": float(total_volume or 0),
    }


@router.get("/admin/transactions", tags=["admin"])
async def list_all_transactions(
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
    skip: int = 0,
    limit: int = 50,
):
    stmt = select(Transaction).offset(skip).limit(limit).order_by(Transaction.created_at.desc())
    result = await db.execute(stmt)
    transactions = result.scalars().all()
    return {
        "transactions": [
            {
                "id": t.id,
                "user_id": t.user_id,
                "symbol": t.symbol,
                "transaction_type": t.transaction_type,
                "quantity": float(t.quantity),
                "price_per_unit": float(t.price_per_unit),
                "total_amount": float(t.total_amount),
                "created_at": str(t.created_at),
            }
            for t in transactions
        ],
        "total": len(transactions),
    }
