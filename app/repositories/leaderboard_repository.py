from typing import List, Dict, Any
import logging
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import User, Portfolio, Transaction

logger = logging.getLogger(__name__)


async def get_leaderboard(db: AsyncSession, limit: int = 10) -> List[Dict[str, Any]]:
    stmt = select(User).where(User.is_active == True).where(User.rol == "inversor")
    result = await db.execute(stmt)
    users = result.scalars().all()

    leaderboard = []

    for user in users:
        portfolio_stmt = select(Portfolio).where(Portfolio.user_id == user.id)
        portfolio_result = await db.execute(portfolio_stmt)
        portfolios = portfolio_result.scalars().all()

        total_portfolio_value = 0
        total_cost = 0

        for p in portfolios:
            total_cost += float(p.quantity) * float(p.average_cost)
            total_portfolio_value += float(p.quantity) * float(p.average_cost) * 1.05

        total_value = float(user.current_balance) + total_portfolio_value
        initial_balance = float(user.initial_balance)

        if initial_balance > 0:
            profitability = ((total_value - initial_balance) / initial_balance) * 100
        else:
            profitability = 0

        leaderboard.append({
            "user_id": user.id,
            "username": user.username,
            "initial_balance": initial_balance,
            "current_balance": float(user.current_balance),
            "portfolio_value": round(total_portfolio_value, 2),
            "total_value": round(total_value, 2),
            "profitability": round(profitability, 2)
        })

    leaderboard.sort(key=lambda x: x["profitability"], reverse=True)

    for i, entry in enumerate(leaderboard):
        entry["rank"] = i + 1

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