# syntax=docker/dockerfile:1
# Web image: FastAPI (/api/*) + the built React SPA. Build context = repo root:
#   docker build -f apps/api/Dockerfile -t seeing-web:dev .

# ---- 1. Build the SPA ---------------------------------------------------------------------------
FROM node:20-alpine AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
RUN npm run build

# ---- 2. Resolve Python dependencies from poetry.lock into a venv ------------------------------
FROM python:3.12-slim AS python-build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install "poetry==1.8.3"
COPY packages/seeing_db /src/packages/seeing_db
COPY apps/api /src/apps/api
WORKDIR /src/apps/api
# Third-party deps pinned by the lock file; the local path packages are installed afterwards.
RUN poetry export --only main --without-hashes -f requirements.txt -o /tmp/req.txt \
    && grep -viE '^(-e )?(seeing-db|file:)' /tmp/req.txt > /tmp/req-thirdparty.txt \
    && python -m venv /opt/venv \
    && /opt/venv/bin/pip install -r /tmp/req-thirdparty.txt \
    && /opt/venv/bin/pip install --no-deps /src/packages/seeing_db /src/apps/api

# ---- 3. Runtime ---------------------------------------------------------------------------------
FROM python:3.12-slim
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STATIC_DIR=/app/static \
    PORT=8080
RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin app
COPY --from=python-build /opt/venv /opt/venv
COPY --from=web /web/dist /app/static
WORKDIR /app
USER app
EXPOSE 8080
# Shell form so $PORT (set by Cloud Run) expands; `exec` keeps uvicorn as PID 1 for signals.
# The same image runs migrations: `seeing-migrate` (Cloud Run job seeing-migrate-{env}).
CMD exec uvicorn seeing_api.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'
