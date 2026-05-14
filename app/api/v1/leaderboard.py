from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.repositories.leaderboard_repository import get_leaderboard, get_user_rank
from app.core.security import get_current_user_id
from app.models.base import User

router = APIRouter()


@router.get("")
async def get_global_leaderboard(
    db: AsyncSession = Depends(get_db),
    limit: int = 10
):
    leaderboard = await get_leaderboard(db, limit=limit)
    return {
        "leaderboard": leaderboard,
        "total": len(leaderboard)
    }


@router.get("/me")
async def get_my_rank(
    db: AsyncSession = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    user_rank = await get_user_rank(db, current_user_id)
    return user_rank