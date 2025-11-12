# syntax=docker/dockerfile:1.7

# ----- Base builder for dependencies (build wheels) -----
FROM python:3.13.1-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100

# Install build deps only where needed
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       gcc \
       libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency manifests first for better caching
COPY requirements.txt /app/requirements.txt

# Build wheels to speed up final image install
RUN pip wheel --wheel-dir=/wheels -r /app/requirements.txt


# ----- Final runtime image -----
FROM python:3.13.1-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UVICORN_WORKERS=1 \
    GUNICORN_TIMEOUT=60 \
    GUNICORN_MAX_REQUESTS=10000 \
    GUNICORN_GRACEFUL_TIMEOUT=30

# System runtime deps only (psycopg requires libpq)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libpq5 \
       openssl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user and group
RUN groupadd -g 1001 appuser \
    && useradd -u 1001 -g appuser -s /usr/sbin/nologin -m appuser

WORKDIR /app

# Copy prebuilt wheels and install
COPY --from=builder /wheels /wheels
COPY requirements.txt /app/requirements.txt
RUN pip install --no-index --find-links=/wheels -r /app/requirements.txt \
    && rm -rf /wheels

# Copy application code
COPY src /app/src

# Adjust ownership
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8080

# Healthcheck: basic TCP check via python
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python - <<'PY' || exit 1
import socket, sys
s=socket.socket()
try:
    s.settimeout(3)
    s.connect(("127.0.0.1", 8080))
    sys.exit(0)
except Exception:
    sys.exit(1)
finally:
    s.close()
PY

# Default command (can be overridden). Bind address and workers configurable via env.
CMD ["gunicorn", 
     "-k", "uvicorn.workers.UvicornWorker", 
     "src.main:app", 
     "--bind", "0.0.0.0:8080", 
     "--workers", "1", 
     "--timeout", "60", 
     "--graceful-timeout", "30", 
     "--max-requests", "10000"]
