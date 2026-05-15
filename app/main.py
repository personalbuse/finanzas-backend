from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import importlib
import logging
import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.core.rate_limiter import limiter, rate_limit_exceeded_handler
from app.core.redis_client import close_redis_client
from slowapi.errors import RateLimitExceeded

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


def create_application() -> FastAPI:
    app = FastAPI(
        title="Simulador de Inversiones API",
        description="API REST para simulador de inversiones en bolsa extranjera",
        version="2.0.0",
        debug=settings.ENVIRONMENT == "development"
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
    elif settings.ENVIRONMENT == "production":
        cors_origins = [settings.FRONTEND_URL.rstrip("/")]
    elif settings.CORS_ORIGINS == "*":
        cors_origins = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=cors_origins != ["*"],
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["Authorization"],
        max_age=3600,
    )

    @app.middleware("http")
    async def maintenance_middleware(request: Request, call_next):
        if request.url.path in MAINTENANCE_SKIP_PATHS or request.url.path.startswith("/api/v1/admin"):
            return await call_next(request)

        if getattr(app.state, "maintenance_mode", False):
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                try:
                    import jwt
                    payload = jwt.decode(auth_header[7:], settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
                    if payload.get("rol") == "admin":
                        return await call_next(request)
                except jwt.PyJWTError:
                    pass
            return JSONResponse(
                status_code=503,
                content={"detail": "Sistema en mantenimiento. Intenta más tarde.", "maintenance": True},
            )

        return await call_next(request)
    
    app.include_router(
        importlib.import_module("app.api.v1.authentication").router,
        prefix="/api/v1",
        tags=["autenticación"]
    )
    app.include_router(
        importlib.import_module("app.api.v1.world").router,
        prefix="/api/v1",
        tags=["world_markets", "indices", "international"]
    )
    app.include_router(
        importlib.import_module("app.api.v1.stocks").router,
        prefix="/api/v1",
        tags=["acciones", "moneda"]
    )
    app.include_router(
        importlib.import_module("app.api.v1.portfolio").router,
        prefix="/api/v1",
        tags=["portafolio"]
    )
    app.include_router(
        importlib.import_module("app.api.v1.learning").router,
        prefix="/api/v1",
        tags=["learning"]
    )
    app.include_router(
        importlib.import_module("app.api.v1.admin").router,
        prefix="/api/v1",
        tags=["admin"]
    )
    app.include_router(
        importlib.import_module("app.api.v1.news").router,
        prefix="/api/v1/news",
        tags=["news"]
    )
    app.include_router(
        importlib.import_module("app.api.v1.leaderboard").router,
        prefix="/api/v1/leaderboard",
        tags=["leaderboard"]
    )
    
    @app.get("/")
    async def root():
        return {
            "message": "Simulador de Inversiones API",
            "version": "2.0.0",
            "status": "running",
            "features": ["rate_limiting", "redis_cache"]
        }
    
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
    
    @app.on_event("startup")
    async def startup_event():
        logger.info("Starting Simulador de Inversiones API v2.0.0")
        logger.info(f"Environment: {settings.ENVIRONMENT}")
        logger.info(f"Redis: {'enabled' if settings.REDIS_URL else 'disabled (fallback to PostgreSQL)'}")
        
        app.state.maintenance_mode = False
        try:
            from sqlalchemy import select, text
            from app.db.session import AsyncSessionLocal
            from app.models.base import SystemConfig
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(SystemConfig).where(SystemConfig.key == "maintenance_mode"))
                config = result.scalar_one_or_none()
                if config and config.value == "true":
                    app.state.maintenance_mode = True
                    logger.info("Sistema iniciado en MODO MANTENIMIENTO")
        except Exception:
            logger.info("No se pudo leer maintenance_mode de BD, usando default: False")
        
        # Configurar APScheduler para actualización diaria a las 00:01 Colombia (UTC 05:01)
        from app.services.finnhub_service import preload_stocks_task
        from app.services.exchange_rate_service import preload_exchange_rates_task

        scheduler.add_job(
            preload_stocks_task,
            'cron',
            hour=5,
            minute=1,
            timezone='America/Bogota'
        )
        scheduler.add_job(
            preload_exchange_rates_task,
            'cron',
            hour=5,
            minute=5,
            timezone='America/Bogota'
        )
        scheduler.start()
        logger.info("Scheduler configurado para actualización diaria a las 00:01 Colombia")

        if settings.ENABLE_STARTUP_PRELOAD:
            asyncio.create_task(preload_stocks_task())
            asyncio.create_task(preload_exchange_rates_task())
            logger.info("Preload inicial iniciado en background (stocks + tasas de cambio)")
    
    @app.on_event("shutdown")
    async def shutdown_event():
        scheduler.shutdown()
        await close_redis_client()
        logger.info("Application shutdown complete")
    
    return app


app = create_application()
