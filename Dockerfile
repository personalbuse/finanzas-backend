FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/app /app/app
COPY src/db /app/db
COPY src/models /app/models
COPY src/schemas /app/schemas
COPY src/services /app/services
COPY src/utils /app/utils
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic
RUN python -c "import sys; print('Dependencies installed successfully')"
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
