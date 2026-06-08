import os
import secrets
from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

current_file_path = Path(__file__).resolve()
backend_dir = current_file_path.parent.parent.parent
env_path = backend_dir / ".env"

DEFAULT_DEV_SECRET = "super_secret_key_change_in_production"


class Settings(BaseSettings):
    DATABASE_URL: str
    EXCHANGE_RATE_API_KEY: str
    FINNHUB_API_KEY: str
    SECRET_KEY: str = Field(..., min_length=64)
    JWT_AUDIENCE: str = "simulador-fiup"
    JWT_ISSUER: str = "simulador-fiup-api"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ENVIRONMENT: str = "development"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CACHE_TTL_SECONDS: int = 300
    STOCK_CACHE_TTL_SECONDS: int = 900
    REDIS_URL: str = ""
    RATE_LIMIT_PER_MINUTE: int = 60
    CORS_ORIGINS: str = ""
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = ""
    FRONTEND_URL: str = ""
    ADMIN_API_KEY: str = ""
    ENABLE_STARTUP_PRELOAD: bool = True
    TRUST_PROXY: bool = False

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if v == DEFAULT_DEV_SECRET:
            raise ValueError(
                "SECRET_KEY must be changed from the default value. "
                "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(64))'"
            )
        if len(v) < 64:
            raise ValueError("SECRET_KEY must be at least 64 characters")
        return v

    @field_validator("CORS_ORIGINS")
    @classmethod
    def validate_cors(cls, v: str) -> str:
        if v == "*":
            import warnings
            warnings.warn(
                "CORS_ORIGINS='*' is not recommended for production. "
                "Use a comma-separated list of allowed origins.",
                stacklevel=2,
            )
        return v

    @field_validator("ADMIN_API_KEY")
    @classmethod
    def validate_admin_key(cls, v: str) -> str:
        if v and len(v) < 32:
            raise ValueError("ADMIN_API_KEY must be at least 32 characters")
        return v

    model_config = SettingsConfigDict(
        env_file=str(env_path) if env_path.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
