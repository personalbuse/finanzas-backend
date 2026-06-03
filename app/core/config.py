import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

current_file_path = Path(__file__).resolve()
backend_dir = current_file_path.parent.parent.parent
env_path = backend_dir / ".env"

class Settings(BaseSettings):
    DATABASE_URL: str
    EXCHANGE_RATE_API_KEY: str
    FINNHUB_API_KEY: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ENVIRONMENT: str = "development"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CACHE_TTL_SECONDS: int = 300
    STOCK_CACHE_TTL_SECONDS: int = 900
    REDIS_URL: str = ""
    RATE_LIMIT_PER_MINUTE: int = 60
    CORS_ORIGINS: str = "*"
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = ""
    FRONTEND_URL: str = ""
    ADMIN_API_KEY: str = ""
    ENABLE_STARTUP_PRELOAD: bool = True

    model_config = SettingsConfigDict(
        env_file=str(env_path) if env_path.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
