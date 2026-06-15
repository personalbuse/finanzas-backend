import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from app.core.config import settings

logger = logging.getLogger(__name__)


def get_client_ip(request: Request) -> str:
    """
    Get the real client IP. Uses X-Real-IP from nginx when TRUST_PROXY is enabled.
    Falls back to direct connection IP. Never uses X-Forwarded-For directly
    to prevent spoofing (only nginx sets X-Real-IP).
    """
    if settings.TRUST_PROXY:  # pragma: no cover
        real_ip = request.headers.get("X-Real-IP")  # pragma: no cover
        if real_ip:  # pragma: no cover
            return real_ip.strip()  # pragma: no cover
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=get_client_ip)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):  # pragma: no cover
    logger.warning(f"Rate limit exceeded for IP: {get_client_ip(request)} path={request.url.path}")
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Demasiadas solicitudes. Intenta de nuevo más tarde.",
            "error": "rate_limit_exceeded",
            "retry_after": getattr(exc, "retry_after", 60),
        },
    )


auth_rate_limit = "5/minute"
stocks_rate_limit = "10/minute"
portfolio_rate_limit = "30/minute"
general_rate_limit = "60/minute"
