from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import importlib
import logging

from app.core.config import settings
from app.core.rate_limiter import limiter, rate_limit_exceeded_handler
from app.core.redis_client import close_redis_client
from slowapi.errors import RateLimitExceeded

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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
    
    @app.on_event("shutdown")
    async def shutdown_event():
        await close_redis_client()
        logger.info("Application shutdown complete")
    
    return app


app = create_application()