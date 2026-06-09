import logging
from typing import Optional
from pydantic import SecretStr

from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_val(key: Optional[SecretStr]) -> str:
    return key.get_secret_value() if key else ""


class ApiKeys:
    EXCHANGE_RATE = _get_val(settings.EXCHANGE_RATE_API_KEY)
    FINNHUB = _get_val(settings.FINNHUB_API_KEY)


def validate_api_keys():
    missing = []
    if not _get_val(settings.FINNHUB_API_KEY):
        missing.append("FINNHUB_API_KEY")
    if not _get_val(settings.EXCHANGE_RATE_API_KEY):
        missing.append("EXCHANGE_RATE_API_KEY")
    if not _get_val(settings.RESEND_API_KEY):
        missing.append("RESEND_API_KEY")

    if missing:
        logger.warning("Missing API keys: %s. Some features may be limited.", ", ".join(missing))

    return len(missing) == 0
