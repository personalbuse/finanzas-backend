# finanzas-backend

REST API for a stock market investment simulator. Built with FastAPI and PostgreSQL, designed to be deployed as a standalone service on Dokploy.

## Architecture

```
backend/
  app/                    # Application code
    api/v1/               # API routes (FastAPI routers)
      authentication.py   # Login, register, password reset, 2FA
      stocks.py           # Stock prices, batch queries, historical data
      portfolio.py        # Buy/sell, portfolio values, transaction history
      learning.py         # Educational modules
      admin.py            # Admin endpoints (user management, KPIs)
    core/                 # Cross-cutting concerns
      config.py           # Environment-based settings
      security.py         # JWT validation, admin API key check
      rate_limiter.py     # Request rate limiting
      redis_client.py     # Redis connection manager
      exceptions.py       # Custom exception classes
      api_keys.py         # External API key management
    db/                   # Database layer
      session.py          # Async engine and session factory
      init.py             # Table creation and connection check
    models/
      base.py             # SQLAlchemy models (User, Portfolio, Transaction, etc.)
    repositories/         # Data access layer
      portfolio_repository.py
      user_repository.py
    schemas/              # Pydantic request/response models
    services/             # Business logic
      auth_service.py     # JWT creation, password hashing, user authentication
      finnhub_service.py  # Stock price fetching via Finnhub API
      exchange_rate_service.py  # Currency conversion via ExchangeRate-API
      cache_service.py    # Redis + PostgreSQL cache layer
      email_service.py    # Email sending via Resend
      redis_2fa_service.py # 2FA code management via Redis
  alembic/                # Database migrations
  Dockerfile              # Docker image for Dokploy deployment
```

## Tech Stack

- Python 3.12+
- FastAPI 0.135
- SQLAlchemy 2.0 (async with asyncpg)
- Alembic for migrations
- Redis for caching and 2FA
- PostgreSQL (Neon or self-hosted)
- JWT authentication (PyJWT)
- Rate limiting (SlowAPI)

## Database Models

| Model | Table | Description |
|-------|-------|-------------|
| User | users | User accounts with balances, roles, and activity status |
| Portfolio | portfolios | Stock holdings per user (composite PK: user_id + symbol) |
| Transaction | transactions | Buy/sell records |
| CacheData | cache_data | Key-value cache with expiration |
| PasswordResetToken | password_reset_tokens | Password reset flow |
| VerificationCode | verification_codes | 2FA and email verification |
| ExchangeRateHistory | exchange_rate_history | Daily exchange rate history |

## Prerequisites

- Python 3.12+
- PostgreSQL database (local, Neon, or Docker)
- Redis (optional, falls back to PostgreSQL caching)
- API keys: Finnhub, ExchangeRate-API, Resend (for emails)

## Setup

```bash
# Clone the repository
git clone https://github.com/personalbuse/finanzas-backend.git
cd finanzas-backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or .\venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your database URL and API keys

# Run migrations
alembic upgrade head

# Start the server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Environment Variables

### Required
| Variable | Description |
|----------|-------------|
| DATABASE_URL | PostgreSQL connection URL (asyncpg format) |
| FINNHUB_API_KEY | API key for stock price data |
| EXCHANGE_RATE_API_KEY | API key for currency conversion |
| SECRET_KEY | JWT signing key (generate with `openssl rand -hex 32`) |

### Optional (with defaults)
| Variable | Default | Description |
|----------|---------|-------------|
| ALGORITHM | HS256 | JWT signing algorithm |
| ACCESS_TOKEN_EXPIRE_MINUTES | 30 | JWT token lifetime |
| ENVIRONMENT | development | Controls debug mode and logging |
| REDIS_URL | (empty) | Redis connection (PostgreSQL fallback if empty) |
| CACHE_TTL_SECONDS | 300 | Cache duration for stock prices |
| RATE_LIMIT_PER_MINUTE | 60 | Global rate limit |
| CORS_ORIGINS | * | Allowed CORS origins |
| FRONTEND_URL | http://localhost:5173 | Frontend URL for email links |
| RESEND_API_KEY | (empty) | Email sending via Resend |
| EMAIL_FROM | (empty) | Sender address for emails |
| ADMIN_API_KEY | (empty) | Shared key for admin endpoints |
| ENABLE_STARTUP_PRELOAD | true | Preload stocks on startup |
| HOST | 0.0.0.0 | Server bind address |
| PORT | 8000 | Server port |

## API Endpoints

### Authentication
```
POST /api/v1/register-init      - Start registration (sends verification code)
POST /api/v1/register-verify    - Complete registration with code
POST /api/v1/resend-code        - Resend verification code
POST /api/v1/login              - Login, returns JWT token
POST /api/v1/forgot-password    - Request password reset
POST /api/v1/reset-password     - Complete password reset with token
GET  /api/v1/profile            - Get current user profile
```

### Stocks
```
GET  /api/v1/stocks/{symbol}         - Get stock price
POST /api/v1/stocks/batch            - Get multiple stock prices
GET  /api/v1/stocks/{symbol}/history - Get historical data
```

### Portfolio
```
GET  /api/v1/portfolio               - Get portfolio values
POST /api/v1/portfolio/buy           - Buy stocks
POST /api/v1/portfolio/sell          - Sell stocks
GET  /api/v1/portfolio/history       - Get transaction history
```

### Exchange Rates
```
GET  /api/v1/exchange-rate           - Get exchange rate
GET  /api/v1/exchange-rate/convert   - Convert currency
GET  /api/v1/exchange-rates/multi    - Get multiple rates with history
```

### Admin (requires admin role in JWT)
```
GET    /api/v1/admin/users                 - List users
GET    /api/v1/admin/users/{id}            - User details
PATCH  /api/v1/admin/users/{id}/role       - Change user role
PATCH  /api/v1/admin/users/{id}/ban        - Toggle user ban
PATCH  /api/v1/admin/users/{id}/balance    - Adjust user balance
GET    /api/v1/admin/kpis                  - System KPIs
GET    /api/v1/admin/transactions          - All transactions
```

### Admin (requires X-Admin-Token header)
```
POST /api/v1/stocks/preload       - Preload all stocks into cache
POST /api/v1/stocks/refresh       - Refresh stocks in background
POST /api/v1/stocks/refresh-sync  - Refresh stocks synchronously
```

## Deployment

This service is designed to be deployed as a container on Dokploy. See `Dockerfile` for the container build process.

```bash
# Build the Docker image
docker build -t finanzas-backend .

# Run with required environment variables
docker run -p 8000:8000 \
  -e DATABASE_URL=postgresql+asyncpg://... \
  -e SECRET_KEY=... \
  -e FINNHUB_API_KEY=... \
  finanzas-backend
```

The server runs `alembic upgrade head` automatically on startup before launching uvicorn.
