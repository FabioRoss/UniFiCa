# ── Stage 1: build the PWA ────────────────────────────────────
FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python runtime (API + scraper + built PWA) ───────
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    OPENUNIFI_DATA_DIR=/data

# Layout mirrors the repo: config.py finds the SPA at ../../frontend/dist
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY backend/app backend/app
COPY --from=frontend /build/dist frontend/dist

WORKDIR /app/backend
VOLUME ["/data"]
EXPOSE 8000
# Single worker on purpose: the scheduler and the Telegram bot run inside
# the process, and SQLite wants one writer.
# --proxy-headers so the app sees https and the real host behind Caddy.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
