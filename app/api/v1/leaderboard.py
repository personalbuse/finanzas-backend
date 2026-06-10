from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.base import User
from app.repositories.leaderboard_repository import get_leaderboard, get_user_rank
from app.services.auth_service import get_current_user, get_token_from_request

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
    current_user: User = Depends(get_authenticated_user)
):
    user_rank = await get_user_rank(db, current_user.id)
    return user_rank
