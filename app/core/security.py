import secrets
from typing import Optional

from fastapi import Header, HTTPException, status

from app.core.config import settings


def _admin_key() -> str:
    return settings.ADMIN_API_KEY.get_secret_value() if settings.ADMIN_API_KEY else ""


def require_admin_api_key(x_admin_token: Optional[str] = Header(default=None)) -> None:
    key = _admin_key()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recurso no encontrado",
        )

    if not x_admin_token or not secrets.compare_digest(x_admin_token, key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos suficientes",
        )
