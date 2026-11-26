# ── Base: system dependencies ─────────────────────────────────────────────────
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ── Install: Python dependencies (isolated prefix build) ─────────────────────
FROM base AS install

WORKDIR /build

COPY pyproject.toml README.md ./
COPY app/ ./app/
# Install runtime deps only (no dev extras) in an isolated prefix
RUN pip install --prefix=/install .


# ── Final: lean runtime image ─────────────────────────────────────────────────
FROM base AS final

WORKDIR /app

# Copy installed packages from the install stage
COPY --from=install /install /usr/local

# Copy application source and configuration
COPY alembic.ini .
COPY README.md .
COPY app/ ./app/

# Create artifacts directory and configure non-root user for security
RUN mkdir -p /app/artifacts && \
    groupadd --system appgroup && \
    useradd --system --gid appgroup --no-create-home appuser && \
    chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
