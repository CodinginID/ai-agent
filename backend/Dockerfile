# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt \
    && find /install -depth \
        \( -type d -a \( -name tests -o -name test -o -name __pycache__ \) \
        -o -type f -a -name '*.pyc' \) \
        -exec rm -rf {} +

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

# Baked build version — surfaced by GET /health. release.yml passes the tag via
# --build-arg APP_VERSION=<tag>; defaults to "dev" for local builds.
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

RUN mkdir -p /app/data

CMD ["python", "-m", "app.main"]
