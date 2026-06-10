import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Portfolio, User
from app.services.cache_service import CacheService

logger = logging.getLogger(__name__)

CACHE_PREFIX = "leaderboard"
CACHE_TTL_SECONDS = 300


async def get_leaderboard(db: AsyncSession, limit: int = 10) -> list[dict[str, Any]]:
    cache_key = f"{CACHE_PREFIX}:all"
    cached = await CacheService.get(db, CACHE_PREFIX, "all")
    if cached:
        return cached[:limit]

    stmt = (
        select(
            User.id,
            User.username,
            User.initial_balance,
            User.current_balance,
            func.coalesce(func.sum(Portfolio.quantity * Portfolio.average_cost), 0).label('total_cost')
        )
        .outerjoin(Portfolio, User.id == Portfolio.user_id)
        .where(User.is_active == True, User.rol == "inversor")
        .group_by(User.id, User.username, User.initial_balance, User.current_balance)
    )
    result = await db.execute(stmt)
    rows = result.all()

    leaderboard = []
    for row in rows:
        total_cost = float(row.total_cost)
        total_portfolio_value = total_cost * 1.05
        total_value = float(row.current_balance) + total_portfolio_value
        initial_balance = float(row.initial_balance)

        if initial_balance > 0:
            profitability = ((total_value - initial_balance) / initial_balance) * 100
        else:
            profitability = 0

        leaderboard.append({
            "user_id": row.id,
            "username": row.username,
            "initial_balance": initial_balance,
            "current_balance": float(row.current_balance),
            "portfolio_value": round(total_portfolio_value, 2),
            "total_value": round(total_value, 2),
            "profitability": round(profitability, 2)
        })

    leaderboard.sort(key=lambda x: x["profitability"], reverse=True)

    for i, entry in enumerate(leaderboard):
        entry["rank"] = i + 1

    await CacheService.set(db, CACHE_PREFIX, "all", value=leaderboard, ttl_seconds=CACHE_TTL_SECONDS)
    return leaderboard[:limit]


async def get_user_rank(db: AsyncSession, user_id: int) -> dict[str, Any]:
    leaderboard = await get_leaderboard(db, limit=1000)

    user_entry = next((entry for entry in leaderboard if entry["user_id"] == user_id), None)

    if user_entry:
        return {
            "rank": user_entry["rank"],
            "total_users": len(leaderboard),
            "profitability": user_entry["profitability"],
            "total_value": user_entry["total_value"]
        }

    return {
        "rank": None,
        "total_users": len(leaderboard),
        "profitability": 0,
        "total_value": 0
    }


async def invalidate_leaderboard_cache(db: AsyncSession) -> None:
    await CacheService.invalidate_prefix(db, CACHE_PREFIX)
