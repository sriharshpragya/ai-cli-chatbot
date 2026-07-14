# ============================================
# Production Dockerfile
# ============================================
FROM python:3.11-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash appuser
COPY --from=builder /install /usr/local

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --chown=appuser:appuser . .
USER appuser

# EXPOSE 8000 (COMMENTED OUT FOR RAILWAY)
# NO EXPOSE - Railway sets PORT dynamically
# NO HEALTHCHECK in Dockerfile - Railway does its own healthcheck

# Use $PORT from Railway environment
CMD alembic upgrade head && uvicorn api:app --host 0.0.0.0 --port $PORT --workers 2
