from app.core.config import settings


class ApiKeys:
    ALPHA_VANTAGE = settings.ALPHA_VANTAGE_API_KEY
    EXCHANGE_RATE = settings.EXCHANGE_RATE_API_KEY
    FINNHUB = settings.FINNHUB_API_KEY


def validate_api_keys():
    missing = []
    if not settings.ALPHA_VANTAGE_API_KEY:
        missing.append("ALPHA_VANTAGE_API_KEY")
    if not settings.EXCHANGE_RATE_API_KEY:
        missing.append("EXCHANGE_RATE_API_KEY")
    
    if missing:
        print(f"⚠️  Advertencia: Faltan API keys: {', '.join(missing)}. Algunas funcionalidades pueden estar limitadas.")
    
    return len(missing) == 0
