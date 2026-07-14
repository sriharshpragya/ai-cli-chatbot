# ============================================
# Production Dockerfile
# Multi-stage build for smaller image
# ============================================

# ====== BUILD STAGE ======
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ====== RUNTIME STAGE ======
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user FIRST
RUN useradd --create-home --shell /bin/bash appuser

# Copy Python packages from builder to system location
COPY --from=builder /install /usr/local

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy application code with correct ownership
COPY --chown=appuser:appuser . .

USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

EXPOSE 8000

# Run migrations then start the API (api.py, not main.py which is CLI)
CMD ["sh", "-c", "alembic upgrade head && uvicorn api:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
