from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.user import UserResponse, CourseProgressResponse
from app.services.auth_service import get_current_user
from app.models.base import User
from app.repositories.user_repository import get_course_progress, complete_module

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/login")


@router.get(
    "/course-progress",
    response_model=CourseProgressResponse,
    tags=["learning"]
)
async def get_progress(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    user = await get_current_user(db, token)
    progress = await get_course_progress(db, user.id)
    return progress


@router.post(
    "/complete-module/{module_id}",
    response_model=UserResponse,
    tags=["learning"]
)
async def complete_module_endpoint(
    module_id: str,
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):
    if module_id not in ["m1", "m2", "m3", "m4", "m5", "m6"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Módulo inválido"
        )
    
    user = await get_current_user(db, token)
    updated_user = await complete_module(db, user.id)
    
    return updated_user
