export DATABASE_URL ?= postgresql+psycopg://seeing:seeing@localhost:5432/seeing_dev

.PHONY: db-up db-down migrate test

db-up:
	docker compose up -d db

db-down:
	docker compose down

migrate:
	cd packages/seeing_db && poetry run seeing-migrate

test:
	cd packages/seeing_db && poetry run pytest -q

# --- seeing_core / batch ----------------------------------------------------
# Batch persistence tests run against a throwaway Postgres on port 55433.
TEST_PG_URL ?= postgresql+psycopg://seeing:seeing@localhost:55433/seeing_test

.PHONY: test-core test-batch batch-run

test-core:
	cd packages/seeing_core && poetry install -q && poetry run pytest -q

test-batch:
	docker run -d --rm --name core-pg -e POSTGRES_USER=seeing -e POSTGRES_PASSWORD=seeing \
		-e POSTGRES_DB=seeing_test -p 55433:5432 postgres:16-alpine >/dev/null
	until docker exec core-pg pg_isready -U seeing -d seeing_test >/dev/null 2>&1; do sleep 1; done; sleep 1
	cd apps/batch && poetry install -q && DATABASE_URL=$(TEST_PG_URL) poetry run pytest -q; \
		status=$$?; docker stop core-pg >/dev/null; exit $$status

# Local run against DATABASE_URL (run `make migrate` first). ARGS="--run-time 2026-10-13T00:00Z --keep-gribs"
batch-run:
	cd apps/batch && poetry install -q && poetry run seeing-batch run $(ARGS)
