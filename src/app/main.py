from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import importlib
import logging
import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.core.rate_limiter import limiter, rate_limit_exceeded_handler
from app.core.redis_client import close_redis_client
from slowapi.errors import RateLimitExceeded

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
    
    cors_origins = ["*"]
    if settings.CORS_ORIGINS and settings.CORS_ORIGINS != "*":
        cors_origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",")]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["Authorization"],
        max_age=3600,
    )
    
    app.include_router(
        importlib.import_module("app.api.v1.authentication").router, 
        prefix="/api/v1", 
        tags=["autenticación"]
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
        return {
            "status": "healthy",
            "database": "connected",
            "cache": "redis" if settings.REDIS_URL else "postgresql"
        }
    
    @app.on_event("startup")
    async def startup_event():
        logger.info("Starting Simulador de Inversiones API v2.0.0")
        logger.info(f"Environment: {settings.ENVIRONMENT}")
        logger.info(f"Redis: {'enabled' if settings.REDIS_URL else 'disabled (fallback to PostgreSQL)'}")
        
        # Configurar APScheduler para actualización diaria a las 00:01 Colombia (UTC 05:01)
        from app.services.finnhub_service import preload_stocks_task
        scheduler.add_job(
            preload_stocks_task,
            'cron',
            hour=5,
            minute=1,
            timezone='America/Bogota'
        )
        scheduler.start()
        logger.info("Scheduler configurado para actualización diaria a las 00:01 Colombia")
        
        # Ejecutar preload inicial en background (sin bloquear startup)
        asyncio.create_task(preload_stocks_task())
        logger.info("Preload inicial iniciado en background")
    
    @app.on_event("shutdown")
    async def shutdown_event():
        scheduler.shutdown()
        await close_redis_client()
        logger.info("Application shutdown complete")
    
    return app


app = create_application()