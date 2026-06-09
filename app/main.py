import asyncio
import importlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.rate_limiter import limiter, rate_limit_exceeded_handler
from app.core.redis_client import close_redis_client

MAINTENANCE_SKIP_PATHS = {
    "/health", "/", "/api/v1/login", "/api/v1/register-init", "/api/v1/register-verify",
    "/api/v1/forgot-password", "/api/v1/reset-password",
}

if settings.ENVIRONMENT == "production":
    logging.basicConfig(level=logging.WARNING)
else:
    logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Modern lifespan context manager replacing deprecated on_event."""
    logger.info("Starting Simulador de Inversiones API v2.0.0")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Redis: {'enabled' if settings.REDIS_URL else 'disabled (fallback to PostgreSQL)'}")

    app.state.maintenance_mode = False
    try:
        from sqlalchemy import select
        from app.db.session import AsyncSessionLocal
        from app.models.base import SystemConfig
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SystemConfig).where(SystemConfig.key == "maintenance_mode")
            )
            config = result.scalar_one_or_none()
            if config and config.value == "true":
                app.state.maintenance_mode = True
                logger.warning("System started in MAINTENANCE MODE")
    except Exception:
        logger.warning("Could not read maintenance_mode from DB, using default: False")

    from app.services.finnhub_service import preload_stocks_task
    from app.services.exchange_rate_service import preload_exchange_rates_task

    scheduler.add_job(
        preload_stocks_task,
        "cron",
        hour=5,
        minute=1,
        timezone="America/Bogota",
    )
    scheduler.add_job(
        preload_exchange_rates_task,
        "cron",
        hour=5,
        minute=5,
        timezone="America/Bogota",
    )
    scheduler.start()
    logger.info("Scheduler configured for daily update at 00:01 Colombia time")

    if settings.ENABLE_STARTUP_PRELOAD:
        asyncio.create_task(preload_stocks_task())
        asyncio.create_task(preload_exchange_rates_task())
        logger.info("Initial preload started in background (stocks + exchange rates)")

    from app.core.api_keys import validate_api_keys
    validate_api_keys()

    yield

    scheduler.shutdown()
    await close_redis_client()
    logger.info("Application shutdown complete")


def create_application() -> FastAPI:
    app = FastAPI(
        title="Simulador de Inversiones API",
        description="API REST para simulador de inversiones en bolsa extranjera",
        version="2.0.0",
        debug=settings.ENVIRONMENT == "development",
        lifespan=lifespan,
    )

    app.state.limiter = limiter

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
        return await rate_limit_exceeded_handler(request, exc)

    cors_origins = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]
    if settings.CORS_ORIGINS and settings.CORS_ORIGINS != "*":
        cors_origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",")]
    elif settings.ENVIRONMENT == "production" and settings.FRONTEND_URL:
        cors_origins = [settings.FRONTEND_URL.rstrip("/")]
    elif settings.CORS_ORIGINS == "*":
        cors_origins = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=cors_origins != ["*"],
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["Authorization", "Content-Type", "X-Requested-With", "Accept-Language"],
        expose_headers=["Authorization"],
        max_age=3600,
    )
    app.add_middleware(GZipMiddleware, minimum_size=500)

    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        if settings.ENVIRONMENT == "production":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response

    @app.middleware("http")
    async def maintenance_middleware(request: Request, call_next):
        if (
            request.url.path in MAINTENANCE_SKIP_PATHS
            or request.url.path.startswith("/api/v1/admin/maintenance")
        ):
            return await call_next(request)

        if getattr(app.state, "maintenance_mode", False):
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Sistema en mantenimiento. Intenta más tarde.",
                    "maintenance": True,
                },
            )

        return await call_next(request)

    app.include_router(
        importlib.import_module("app.api.v1.authentication").router,
        prefix="/api/v1",
        tags=["autenticación"],
    )
    app.include_router(
        importlib.import_module("app.api.v1.world").router,
        prefix="/api/v1",
        tags=["world_markets", "indices", "international"],
    )
    app.include_router(
        importlib.import_module("app.api.v1.stocks").router,
        prefix="/api/v1",
        tags=["acciones", "moneda"],
    )
    app.include_router(
        importlib.import_module("app.api.v1.portfolio").router,
        prefix="/api/v1",
        tags=["portafolio"],
    )
    app.include_router(
        importlib.import_module("app.api.v1.learning").router,
        prefix="/api/v1",
        tags=["learning"],
    )
    app.include_router(
        importlib.import_module("app.api.v1.admin").router,
        prefix="/api/v1",
        tags=["admin"],
    )
    app.include_router(
        importlib.import_module("app.api.v1.news").router,
        prefix="/api/v1/news",
        tags=["news"],
    )
    app.include_router(
        importlib.import_module("app.api.v1.leaderboard").router,
        prefix="/api/v1/leaderboard",
        tags=["leaderboard"],
    )

    @app.get("/")
    async def root():
        return {"status": "ok"}

    @app.get("/health")
    async def health_check():
        db_status = "disconnected"
        try:
            from app.db.session import AsyncSessionLocal
            from sqlalchemy import text
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
                db_status = "connected"
        except Exception:
            db_status = "disconnected"

        return {
            "status": "healthy" if db_status == "connected" else "degraded",
            "database": db_status,
            "cache": "redis" if settings.REDIS_URL else "postgresql",
            "maintenance_mode": getattr(app.state, "maintenance_mode", False),
        }

    return app


app = create_application()
