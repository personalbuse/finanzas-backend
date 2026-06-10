import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CustomException, ValidationException
from app.models.base import User
from app.services.auth_service import get_password_hash

logger = logging.getLogger(__name__)


async def create_user(db: AsyncSession, user_data: Any) -> User:
    username = user_data.username.lower() if isinstance(user_data.username, str) else user_data.username
    stmt = select(User).where(
        (User.username == username) | (User.email == user_data.email)
    )
    result = await db.execute(stmt)
    existing_user = result.scalar_one_or_none()

    if existing_user:
        if existing_user.username == username:
            raise ValidationException(detail="El nombre de usuario ya está en uso")
        if existing_user.email == user_data.email:
            raise ValidationException(detail="El email ya está en uso")

    hashed_password = get_password_hash(user_data.password)

    user = User(
        username=username,
        email=user_data.email,
        hashed_password=hashed_password,
        initial_balance=user_data.initial_balance or 10000.00,
        current_balance=user_data.initial_balance or 10000.00,
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    stmt = select(User).where(User.username == username.lower())
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def update_user_balance(db: AsyncSession, user_id: int, amount: float) -> User:
    stmt = select(User).where(User.id == user_id).with_for_update()
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise CustomException(status_code=404, detail="Usuario no encontrado")

    user.current_balance = float(user.current_balance) + float(amount)
    await db.commit()
    await db.refresh(user)

    return user


async def get_all_users(db: AsyncSession, skip: int = 0, limit: int = 100) -> list[User]:
    stmt = select(User).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_course_progress(db: AsyncSession, user_id: int) -> dict:
    user = await get_user_by_id(db, user_id)
    if not user:
        return {"completed_courses": 0, "bonus_earned": 0}
    return {
        "completed_courses": user.completed_courses or 0,
        "bonus_earned": (user.completed_courses or 0) * 1000,
    }
