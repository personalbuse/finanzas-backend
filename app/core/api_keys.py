from app.core.config import settings


class ApiKeys:
    EXCHANGE_RATE = settings.EXCHANGE_RATE_API_KEY
    FINNHUB = settings.FINNHUB_API_KEY


def validate_api_keys():
    missing = []
    if not settings.FINNHUB_API_KEY:
        missing.append("FINNHUB_API_KEY")
    if not settings.EXCHANGE_RATE_API_KEY:
        missing.append("EXCHANGE_RATE_API_KEY")
    
    if missing:
        print(f"⚠️  Advertencia: Faltan API keys: {', '.join(missing)}. Algunas funcionalidades pueden estar limitadas.")
    
    return len(missing) == 0
