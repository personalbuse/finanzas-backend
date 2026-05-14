from typing import List, Dict, Any
import logging
import asyncio
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import User, Portfolio, Transaction

logger = logging.getLogger(__name__)

_leaderboard_cache: Dict[str, Any] = {"data": None, "timestamp": 0}
CACHE_TTL_SECONDS = 300


def _get_cache_key() -> str:
    return "leaderboard:all"


def _is_cache_valid() -> bool:
    if _leaderboard_cache["data"] is None:
        return False
    import time
    return (time.time() - _leaderboard_cache["timestamp"]) < CACHE_TTL_SECONDS


def _get_cached_leaderboard() -> List[Dict[str, Any]]:
    if _is_cache_valid():
        return _leaderboard_cache["data"]
    return None


def _set_cached_leaderboard(data: List[Dict[str, Any]]) -> None:
    import time
    _leaderboard_cache["data"] = data
    _leaderboard_cache["timestamp"] = time.time()


async def get_leaderboard(db: AsyncSession, limit: int = 10) -> List[Dict[str, Any]]:
    cached = _get_cached_leaderboard()
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

    _set_cached_leaderboard(leaderboard)
    return leaderboard[:limit]


async def get_user_rank(db: AsyncSession, user_id: int) -> Dict[str, Any]:
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


def invalidate_leaderboard_cache() -> None:
    global _leaderboard_cache
    _leaderboard_cache = {"data": None, "timestamp": 0}