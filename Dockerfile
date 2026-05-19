# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: production ───────────────────────────────────────────────────────
FROM python:3.13-slim AS production

WORKDIR /app

# git dibutuhkan runtime untuk git_status action
# curl dibutuhkan untuk healthcheck di docker-compose.yml
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

COPY alembic.ini .
COPY alembic/ ./alembic/
COPY app/ ./app/

RUN mkdir -p /app/data

CMD ["python", "-m", "app.main"]
