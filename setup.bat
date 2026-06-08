@echo off
REM Backend setup script for development
cd /d "%~dp0"
python -m venv venv
call venv\Scripts\activate.bat
pip install -r requirements.txt
pip install pytest pytest-asyncio httpx ruff mypy
alembic upgrade head
echo "Setup complete. Run: uvicorn app.main:app --reload --port 8000"
