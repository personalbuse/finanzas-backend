import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

logger = logging.getLogger(__name__)

from app.core.config import settings
from app.core.exceptions import UnauthorizedException
from app.models.base import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        logger.exception("Error verifying password")
        return False


def get_password_hash(password: str) -> str:
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password=pwd_bytes, salt=salt).decode("utf-8")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
    token_type: str = "access",
) -> str:
    to_encode = data.copy()
    now = _now()
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update(
        {
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int(expire.timestamp()),
            "aud": settings.JWT_AUDIENCE,
            "iss": settings.JWT_ISSUER,
            "jti": secrets.token_urlsafe(16),
            "type": token_type,
        }
    )
    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def create_refresh_token(user: User) -> str:
    return create_access_token(
        data={"sub": user.username, "user_id": user.id, "password_version": getattr(user, "password_version", 0)},
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        token_type="refresh",
    )


def decode_token(token: str, token_type: str = "access") -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
        )
    except jwt.PyJWTError as e:
        raise UnauthorizedException(f"Invalid token: {e}")
    if payload.get("type") != token_type:
        raise UnauthorizedException("Wrong token type")
    return payload


async def authenticate_user(db: AsyncSession, username: str, password: str) -> Optional[User]:
    stmt = select(User).where(User.username == username.lower())
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        return None

    if not verify_password(password, user.hashed_password):
        return None

    return user


async def get_current_user(db: AsyncSession, token: str) -> User:
    payload = decode_token(token, token_type="access")
    username: str = payload.get("sub")
    if username is None:
        raise UnauthorizedException("Invalid credentials")

    stmt = select(User).where(User.username == username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise UnauthorizedException("User not found")

    if not user.is_active:
        raise UnauthorizedException("User is inactive")

    token_pv = payload.get("password_version", 0)
    user_pv = getattr(user, "password_version", 0)
    if token_pv != user_pv:
        raise UnauthorizedException("Token revoked (password changed)")

    return user
