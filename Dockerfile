# Multi-stage production build for Astrology WhatsApp Platform
FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

# Install minimal build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast, reliable package builds
RUN pip install --no-cache-dir uv==0.13.4

# Create virtual environment
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy package specifications and source
COPY packages/astrology-engine /build/packages/astrology-engine
COPY apps/api /build/apps/api

# Install packages into virtual environment
RUN uv pip install --no-cache /build/packages/astrology-engine
RUN uv pip install --no-cache /build/apps/api

# ── Final Runtime Stage ────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

# Install minimal runtime dependencies (libpq5 for PostgreSQL client, curl for healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtualenv from builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/apps/api/src:/app/packages/astrology-engine/src

# Create non-root system user
RUN groupadd -g 10001 astrology && \
    useradd -u 10001 -g astrology -s /bin/bash -m astrology

# Copy application source, migrations, alembic config, static assets, and deployment utilities
COPY --chown=astrology:astrology packages/astrology-engine /app/packages/astrology-engine
COPY --chown=astrology:astrology apps/api /app/apps/api
COPY --chown=astrology:astrology deploy /app/deploy

USER astrology

EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

WORKDIR /app/apps/api

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src"]
