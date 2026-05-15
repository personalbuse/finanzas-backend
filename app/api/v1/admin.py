import json
import jwt
import logging
from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from sqlalchemy import select, func, text, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.rate_limiter import limiter, portfolio_rate_limit
from app.db.session import get_db
from app.models.base import User, Transaction, AdminLog, SystemConfig, CacheData, Portfolio
from app.repositories.portfolio_repository import calculate_portfolio_values
from app.schemas.user import UserResponse

logger = logging.getLogger(__name__)
router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/login")


class RoleRequest(BaseModel):
    new_role: str = Field(..., pattern="^(inversor|admin)$")


class BalanceRequest(BaseModel):
    new_balance: float = Field(..., ge=0)


class ConfigUpdateRequest(BaseModel):
    value: str = Field(..., min_length=1)


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


async def _get_admin_user(username: str, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.username == username))
    admin = result.scalar_one_or_none()
    if not admin:
        raise HTTPException(status_code=404, detail="Admin no encontrado")
    return admin


async def _log_admin_action(
    db: AsyncSession,
    admin_user: User,
    action: str,
    target_type: str,
    target_id: Optional[int] = None,
    details: Optional[dict] = None,
):
    log = AdminLog(
        admin_id=admin_user.id,
        admin_username=admin_user.username,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=json.dumps(details) if details else None,
    )
    db.add(log)


DEFAULT_CONFIGS: dict[str, tuple[str, str]] = {
    "initial_balance": ("10000", "Balance inicial para nuevos usuarios"),
    "course_bonus": ("1000", "Bonus por curso completado"),
    "max_daily_transactions": ("50", "Límite de transacciones diarias por usuario"),
    "maintenance_mode": ("false", "Modo mantenimiento del sistema"),
    "suspicious_threshold": ("50000", "Monto mínimo para considerar transacción sospechosa"),
}


async def _ensure_default_configs(db: AsyncSession):
    for key, (value, description) in DEFAULT_CONFIGS.items():
        existing = await db.execute(select(SystemConfig).where(SystemConfig.key == key))
        if not existing.scalar_one_or_none():
            db.add(SystemConfig(key=key, value=value, description=description))
    await db.commit()


# ────────────────────────── USUARIOS ──────────────────────────


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

    total_stmt = select(func.count(User.id))
    total_result = await db.execute(total_stmt)
    total = total_result.scalar()

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
        "total": total or 0,
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

    tx_result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.created_at.desc())
        .limit(20)
    )
    transactions = tx_result.scalars().all()

    pf_result = await db.execute(
        select(Portfolio).where(Portfolio.user_id == user_id)
    )
    portfolio = pf_result.scalars().all()

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
        "transactions": [
            {
                "id": t.id,
                "symbol": t.symbol,
                "transaction_type": t.transaction_type,
                "quantity": float(t.quantity),
                "price_per_unit": float(t.price_per_unit),
                "total_amount": float(t.total_amount),
                "created_at": str(t.created_at),
            }
            for t in transactions
        ],
        "portfolio": [
            {
                "symbol": p.symbol,
                "quantity": float(p.quantity),
                "average_cost": float(p.average_cost),
            }
            for p in portfolio
        ],
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
    admin_user = await _get_admin_user(admin, db)
    if admin_user.id == user_id:
        raise HTTPException(status_code=403, detail="No puedes cambiar tu propio rol")
    old_role = user.rol
    user.rol = body.new_role
    await _log_admin_action(
        db, admin_user,
        action="role_change",
        target_type="user",
        target_id=user_id,
        details={"username": user.username, "old_role": old_role, "new_role": body.new_role},
    )
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
    admin_user = await _get_admin_user(admin, db)
    if admin_user.id == user_id:
        raise HTTPException(status_code=403, detail="No puedes banearte a ti mismo")
    user.is_active = not user.is_active
    await _log_admin_action(
        db, admin_user,
        action="ban" if not user.is_active else "unban",
        target_type="user",
        target_id=user_id,
        details={"username": user.username, "was_active": not user.is_active},
    )
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
    admin_user = await _get_admin_user(admin, db)
    old_balance = float(user.current_balance)
    user.current_balance = body.new_balance
    await _log_admin_action(
        db, admin_user,
        action="balance_adjust",
        target_type="user",
        target_id=user_id,
        details={"username": user.username, "old_balance": old_balance, "new_balance": body.new_balance},
    )
    await db.commit()
    return {"message": "Saldo actualizado", "user_id": user_id, "new_balance": body.new_balance}


# ────────────────────────── KPIs ──────────────────────────


@router.get("/admin/kpis", tags=["admin"])
async def get_kpis(
    request: Request,
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
        "maintenance_mode": getattr(request.app.state, "maintenance_mode", False),
    }


@router.get("/admin/kpis/evolution", tags=["admin"])
async def get_kpis_evolution(
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
    days: int = Query(365, ge=1, le=1825),
):
    cutoff = datetime.utcnow() - timedelta(days=days)

    month_col = func.date_trunc('month', User.created_at).label('month')
    users_result = await db.execute(
        select(month_col, func.count(User.id).label('count'))
        .where(User.created_at >= cutoff)
        .group_by(month_col)
        .order_by(month_col)
    )
    users_by_month = [
        {"month": str(row.month)[:7], "count": row.count}
        for row in users_result
    ]

    tx_month_col = func.date_trunc('month', Transaction.created_at).label('month')
    volume_result = await db.execute(
        select(
            tx_month_col,
            func.count(Transaction.id).label('count'),
            func.coalesce(func.sum(Transaction.total_amount), 0).label('volume'),
        )
        .where(Transaction.created_at >= cutoff)
        .group_by(tx_month_col)
        .order_by(tx_month_col)
    )
    volume_by_month = [
        {"month": str(row.month)[:7], "transactions": row.count, "volume": float(row.volume)}
        for row in volume_result
    ]

    return {
        "users_by_month": users_by_month,
        "volume_by_month": volume_by_month,
    }


@router.get("/admin/kpis/top-stocks", tags=["admin"])
async def get_top_stocks(
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
    limit: int = Query(10, ge=1, le=50),
):
    top = await db.execute(
        select(
            Transaction.symbol,
            func.count(Transaction.id).label('transaction_count'),
            func.coalesce(func.sum(Transaction.total_amount), 0).label('total_volume'),
            func.sum(Transaction.quantity).label('total_shares'),
        )
        .group_by(Transaction.symbol)
        .order_by(func.count(Transaction.id).desc())
        .limit(limit)
    )
    return {
        "top_stocks": [
            {
                "symbol": row.symbol,
                "transaction_count": row.transaction_count,
                "total_volume": float(row.total_volume),
                "total_shares": float(row.total_shares or 0),
            }
            for row in top
        ]
    }


@router.get("/admin/kpis/distribution", tags=["admin"])
async def get_kpis_distribution(
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
):
    type_dist = await db.execute(
        select(
            Transaction.transaction_type,
            func.count(Transaction.id).label('count'),
            func.coalesce(func.sum(Transaction.total_amount), 0).label('volume'),
        )
        .group_by(Transaction.transaction_type)
    )

    avg_balance = await db.scalar(select(func.avg(User.current_balance)))
    total_courses = await db.scalar(select(func.coalesce(func.sum(User.completed_courses), 0)))
    total_users = await db.scalar(select(func.count(User.id)))
    total_tx = await db.scalar(select(func.count(Transaction.id)))

    return {
        "transaction_types": {
            row.transaction_type: {
                "count": row.count,
                "volume": float(row.volume),
            }
            for row in type_dist
        },
        "average_balance": float(avg_balance or 0),
        "total_completed_courses": total_courses or 0,
        "average_transactions_per_user": round((total_tx or 0) / max(total_users or 1, 1), 2),
    }


# ────────────────────────── TRANSACCIONES ──────────────────────────


@router.get("/admin/transactions", tags=["admin"])
async def list_all_transactions(
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
    skip: int = 0,
    limit: int = 50,
    user_id: Optional[int] = Query(None),
    symbol: Optional[str] = Query(None),
    transaction_type: Optional[str] = Query(None, pattern="^(buy|sell)?$"),
):
    conditions = []
    if user_id is not None:
        conditions.append(Transaction.user_id == user_id)
    if symbol:
        conditions.append(Transaction.symbol == symbol.upper())
    if transaction_type:
        conditions.append(Transaction.transaction_type == transaction_type)

    stmt = select(Transaction)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    stmt = stmt.offset(skip).limit(limit).order_by(Transaction.created_at.desc())

    result = await db.execute(stmt)
    transactions = result.scalars().all()

    count_stmt = select(func.count(Transaction.id))
    if conditions:
        count_stmt = count_stmt.where(and_(*conditions))
    total_result = await db.execute(count_stmt)
    total = total_result.scalar()

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
        "total": total or 0,
    }


@router.get("/admin/suspicious-transactions", tags=["admin"])
async def get_suspicious_transactions(
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
    threshold: float = Query(50000, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    large_tx_result = await db.execute(
        select(Transaction)
        .where(Transaction.total_amount > threshold)
        .order_by(Transaction.total_amount.desc())
        .limit(limit)
    )
    large_tx = large_tx_result.scalars().all()

    suspicious_users_result = await db.execute(
        select(User)
        .where(
            and_(
                User.current_balance > User.initial_balance * 2,
                User.is_active == True,
            )
        )
        .order_by((User.current_balance / User.initial_balance).desc())
        .limit(limit)
    )
    suspicious_users = suspicious_users_result.scalars().all()

    return {
        "large_transactions": [
            {
                "id": t.id,
                "user_id": t.user_id,
                "symbol": t.symbol,
                "transaction_type": t.transaction_type,
                "quantity": float(t.quantity),
                "total_amount": float(t.total_amount),
                "created_at": str(t.created_at),
            }
            for t in large_tx
        ],
        "suspicious_users": [
            {
                "id": u.id,
                "username": u.username,
                "current_balance": float(u.current_balance),
                "initial_balance": float(u.initial_balance),
                "growth_multiplier": round(float(u.current_balance) / float(u.initial_balance), 2),
            }
            for u in suspicious_users
        ],
    }


# ────────────────────────── LOGS DE AUDITORÍA ──────────────────────────


@router.get("/admin/logs", tags=["admin"])
async def get_admin_logs(
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
    skip: int = 0,
    limit: int = 50,
    action: Optional[str] = Query(None),
):
    stmt = select(AdminLog).order_by(AdminLog.created_at.desc())
    if action:
        stmt = stmt.where(AdminLog.action == action)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    logs = result.scalars().all()

    count_stmt = select(func.count(AdminLog.id))
    if action:
        count_stmt = count_stmt.where(AdminLog.action == action)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar()

    return {
        "logs": [
            {
                "id": log.id,
                "admin_id": log.admin_id,
                "admin_username": log.admin_username,
                "action": log.action,
                "target_type": log.target_type,
                "target_id": log.target_id,
                "details": json.loads(log.details) if log.details else None,
                "created_at": str(log.created_at),
            }
            for log in logs
        ],
        "total": total or 0,
    }


# ────────────────────────── CONFIGURACIONES ──────────────────────────


@router.get("/admin/config", tags=["admin"])
async def list_configs(
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
):
    await _ensure_default_configs(db)
    result = await db.execute(select(SystemConfig).order_by(SystemConfig.key))
    configs = result.scalars().all()
    return {
        "configs": [
            {
                "key": c.key,
                "value": c.value,
                "description": c.description,
                "updated_at": str(c.updated_at),
            }
            for c in configs
        ]
    }


@router.put("/admin/config/{key}", tags=["admin"])
async def update_config(
    key: str,
    body: ConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
):
    admin_user = await _get_admin_user(admin, db)
    result = await db.execute(select(SystemConfig).where(SystemConfig.key == key))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail=f"Configuración '{key}' no encontrada")

    old_value = config.value
    config.value = body.value

    await _log_admin_action(
        db, admin_user,
        action="config_update",
        target_type="config",
        details={"key": key, "old_value": old_value, "new_value": body.value},
    )
    await db.commit()

    return {"message": f"Configuración '{key}' actualizada", "key": key, "value": body.value}


@router.post("/admin/maintenance", tags=["admin"])
async def toggle_maintenance(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
):
    admin_user = await _get_admin_user(admin, db)

    await _ensure_default_configs(db)
    result = await db.execute(select(SystemConfig).where(SystemConfig.key == "maintenance_mode"))
    config = result.scalar_one_or_none()

    if not config:
        config = SystemConfig(key="maintenance_mode", value="true", description="Modo mantenimiento del sistema")
        db.add(config)
    else:
        config.value = "false" if config.value == "true" else "true"

    request.app.state.maintenance_mode = config.value == "true"

    await _log_admin_action(
        db, admin_user,
        action="toggle_maintenance",
        target_type="system",
        details={"new_value": config.value},
    )
    await db.commit()

    return {"maintenance_mode": config.value == "true"}


# ────────────────────────── DATOS Y MANTENIMIENTO ──────────────────────────


@router.post("/admin/refresh/stocks", tags=["admin"])
async def refresh_stocks(
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
):
    admin_user = await _get_admin_user(admin, db)
    from app.services.finnhub_service import preload_stocks_task
    try:
        await preload_stocks_task()
        await _log_admin_action(db, admin_user, "refresh_data", "system", details={"type": "stocks"})
        await db.commit()
        return {"message": "Stocks actualizados correctamente"}
    except Exception as e:
        logger.error(f"Error refrescando stocks: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.post("/admin/refresh/rates", tags=["admin"])
async def refresh_exchange_rates(
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
):
    admin_user = await _get_admin_user(admin, db)
    from app.services.exchange_rate_service import preload_exchange_rates_task
    try:
        await preload_exchange_rates_task()
        await _log_admin_action(db, admin_user, "refresh_data", "system", details={"type": "exchange_rates"})
        await db.commit()
        return {"message": "Tasas de cambio actualizadas correctamente"}
    except Exception as e:
        logger.error(f"Error refrescando tasas: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.post("/admin/refresh/indices", tags=["admin"])
async def refresh_indices(
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
):
    admin_user = await _get_admin_user(admin, db)
    from app.services.world_indices_service import preload_world_indices
    try:
        await preload_world_indices(db)
        await _log_admin_action(db, admin_user, "refresh_data", "system", details={"type": "indices"})
        await db.commit()
        return {"message": "Índices mundiales actualizados correctamente"}
    except Exception as e:
        logger.error(f"Error refrescando índices: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.post("/admin/cache/clear", tags=["admin"])
async def clear_cache(
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
):
    admin_user = await _get_admin_user(admin, db)
    from app.core.redis_client import get_redis
    try:
        redis = await get_redis()
        if redis:
            await redis.flushdb()
    except Exception:
        logger.warning("Redis no disponible, limpiando solo caché PostgreSQL")

    await db.execute(CacheData.__table__.delete())

    await _log_admin_action(db, admin_user, "clear_cache", "system")
    await db.commit()

    return {"message": "Caché limpiada correctamente"}


@router.get("/admin/stats/tables", tags=["admin"])
async def get_table_stats(
    db: AsyncSession = Depends(get_db),
    admin: str = Depends(require_admin),
):
    tables = {
        "users": User,
        "transactions": Transaction,
        "portfolios": Portfolio,
        "admin_logs": AdminLog,
        "cache_data": CacheData,
    }
    stats = []
    for name, model in tables.items():
        count = await db.scalar(select(func.count(model.id)))
        stats.append({"table": name, "records": count or 0})
    return {"tables": stats}
