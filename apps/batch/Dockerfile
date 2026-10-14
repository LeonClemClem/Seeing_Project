# Batch job image. Build context = repo root:
#   docker build -f apps/batch/Dockerfile -t seeing-batch:dev .
# ecCodes comes from the `eccodeslib` wheel (bundled C library), no apt package needed.

FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=1.8.3 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1
RUN pip install "poetry==${POETRY_VERSION}"
WORKDIR /app
# Dependency layer first (lock files only), then the sources.
COPY packages/seeing_core/pyproject.toml packages/seeing_core/poetry.lock packages/seeing_core/
COPY packages/seeing_db/pyproject.toml packages/seeing_db/poetry.lock packages/seeing_db/
COPY apps/batch/pyproject.toml apps/batch/poetry.lock apps/batch/
RUN mkdir -p packages/seeing_core/seeing_core packages/seeing_db/seeing_db apps/batch/seeing_batch \
    && touch packages/seeing_core/seeing_core/__init__.py packages/seeing_db/seeing_db/__init__.py \
       apps/batch/seeing_batch/__init__.py \
    && cd apps/batch && poetry install --only main
COPY packages/seeing_core/seeing_core packages/seeing_core/seeing_core
COPY packages/seeing_db/seeing_db packages/seeing_db/seeing_db
COPY apps/batch/seeing_batch apps/batch/seeing_batch
# Path dependencies are installed in develop mode (.pth -> /app/...), so the runtime stage
# keeps the same layout.
RUN cd apps/batch && poetry install --only main \
    && .venv/bin/python -c "import eccodes, seeing_core, seeing_db, seeing_batch.cli; print('ecCodes', eccodes.codes_get_api_version())"

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PATH=/app/apps/batch/.venv/bin:$PATH \
    GRIB_DIR=/tmp/arome
RUN useradd --create-home --uid 10001 seeing
COPY --from=builder /app /app
USER seeing
WORKDIR /home/seeing
ENTRYPOINT ["seeing-batch"]
CMD ["run"]
