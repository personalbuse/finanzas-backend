from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limiter import limiter
from app.db.session import get_db
from app.models.base import CompletedModule, User
from app.repositories.user_repository import get_course_progress
from app.schemas.user import CourseProgressResponse, UserResponse
from app.services.auth_service import get_current_user

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/login")

VALID_MODULES = {"m1", "m2", "m3", "m4", "m5", "m6"}
MODULE_BONUS = 1000


@router.get(
    "/course-progress",
    response_model=CourseProgressResponse,
    tags=["learning"],
)
@limiter.limit("30/minute")
async def get_progress(
    request: Request,
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    user = await get_current_user(db, token)
    progress = await get_course_progress(db, user.id)
    return progress


@router.post(
    "/complete-module/{module_id}",
    response_model=UserResponse,
    tags=["learning"],
)
@limiter.limit("6/hour")
async def complete_module_endpoint(
    request: Request,
    module_id: str,
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    if module_id not in VALID_MODULES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Módulo inválido",
        )

    user = await get_current_user(db, token)

    if user.completed_courses >= 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya has completado todos los módulos",
        )

    completion = CompletedModule(user_id=user.id, module_id=module_id)
    db.add(completion)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este módulo ya fue completado",
        )

    user.completed_courses += 1
    user.current_balance = float(user.current_balance) + MODULE_BONUS
    await db.commit()
    await db.refresh(user)

    return user
