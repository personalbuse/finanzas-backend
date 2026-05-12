from typing import Optional, List, Any
import logging

from app.models.base import User
from app.db.session import get_db
from sqlalchemy import select
from app.core.exceptions import ValidationException, CustomException
from app.services.auth_service import get_password_hash
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def create_user(db: AsyncSession, user_data: Any) -> User:
    stmt = select(User).where(
        (User.username == user_data.username) | 
        (User.email == user_data.email)
    )
    result = await db.execute(stmt)
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        if existing_user.username == user_data.username:
            raise ValidationException(detail="El nombre de usuario ya está en uso")
        if existing_user.email == user_data.email:
            raise ValidationException(detail="El email ya está en uso")
    
    hashed_password = get_password_hash(user_data.password)
    
    user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_password,
        initial_balance=user_data.initial_balance or 10000.00,
        current_balance=user_data.initial_balance or 10000.00
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    return user


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    stmt = select(User).where(User.username == username)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def update_user_balance(db: AsyncSession, user_id: int, amount: float) -> User:
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise CustomException(status_code=404, detail="Usuario no encontrado")
    
    user.current_balance = float(user.current_balance) + float(amount)
    await db.commit()
    await db.refresh(user)
    
    return user


async def get_all_users(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[User]:
    stmt = select(User).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_course_progress(db: AsyncSession, user_id: int) -> dict:
    user = await get_user_by_id(db, user_id)
    if not user:
        return {"completed_courses": 0, "bonus_earned": 0}
    return {
        "completed_courses": user.completed_courses,
        "bonus_earned": user.completed_courses * 1000
    }


async def complete_module(db: AsyncSession, user_id: int) -> User:
    user = await get_user_by_id(db, user_id)
    if not user:
        raise CustomException(status_code=404, detail="Usuario no encontrado")
    
    if user.completed_courses < 6:
        user.completed_courses += 1
        user.current_balance = float(user.current_balance) + 1000
    
    await db.commit()
    await db.refresh(user)
    return user
