FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY backend/app ./app
# Migrations must ship: the app upgrades its own schema on boot.
COPY backend/alembic.ini ./alembic.ini
COPY backend/migrations ./migrations
# Evaluation suites are data, and live a level up from the backend package.
COPY evals ../evals

RUN useradd -m -u 10001 orion && mkdir -p /data /knowledge \
 && chown -R orion:orion /app /evals /data /knowledge
USER orion

ENV DATABASE_URL=sqlite:////data/orion.db \
    KNOWLEDGE_DIR=/knowledge \
    ENVIRONMENT=production

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
