from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=get_client_ip)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    logger.warning(f"Rate limit exceeded for IP: {get_client_ip(request)}")
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Demasiadas solicitudes. Intenta de nuevo más tarde.",
            "error": "rate_limit_exceeded",
            "retry_after": getattr(exc, 'retry_after', 60),
        }
    )


auth_rate_limit = "5/minute"
stocks_rate_limit = "10/minute"
portfolio_rate_limit = "30/minute"
general_rate_limit = "60/minute"
