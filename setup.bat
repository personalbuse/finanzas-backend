# Backend - FastAPI
cd backend

# Crear entorno virtual e instalar dependencias
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
pip install fastapi uvicorn python-dotenv sqlalchemy asyncpg aiosqlite httpx alembic python-jose[cryptography] passlib[bcrypt] starlette

# Crear archivo de requerimientos
cat > requirements.txt << 'EOF'
fastapi==0.109.0
uvicorn==0.27.0
python-dotenv==1.0.0
sqlalchemy==2.0.25
asyncpg==0.29.0
aiosqlite==0.20.0
httpx==0.26.0
alembic==1.13.1
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.9
aiofiles==23.2.1
pandas==2.1.4
EOF

# Crear estructura de archivos
mkdir -p src/app/{api,v1,core,db,models,services,schemas,utils}
touch src/app/__init__.py src/app/api/__init__.py src/app/api/v1/__init__.py src/app/core/__init__.py src/app/db/__init__.py src/app/models/__init__.py src/app/services/__init__.py src/app/schemas/__init__.py src/app/utils/__init__.py

cat > .env.example << 'EOF'
# PostgreSQL Neon
DATABASE_URL=postgresql://user:password@ep-xxx-xxx.aws.neon.tech/dbname?sslmode=require

# API Keys
ALPHA_VANTAGE_API_KEY=tu_alpha_vantage_api_key
EXCHANGE_RATE_API_KEY=tu_exchange_rate_api_key

# JWT
SECRET_KEY=tu_secret_key_super_segura_aqui
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# App
ENVIRONMENT=development
HOST=0.0.0.0
PORT=8000
EOF
