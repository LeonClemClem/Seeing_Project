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

# ---- Web (apps/api + apps/web) ----------------------------------------------------------------
TEST_PG := web-pg
export TEST_DATABASE_URL ?= postgresql+psycopg://seeing:seeing@localhost:55434/seeing_test

.PHONY: api-install web-install api-dev web-dev dev-seed test-api test-web web-image

api-install:
	cd apps/api && poetry install

web-install:
	cd apps/web && npm ci

# FastAPI on :8000 with reload (uses DATABASE_URL; run `make db-up migrate dev-seed` first).
api-dev:
	cd apps/api && STATIC_DIR=$${STATIC_DIR:-../web/dist} poetry run uvicorn seeing_api.main:app --reload --port 8000

# Vite on :5173, proxies /api to :8000.
web-dev:
	cd apps/web && npm run dev

# Insert a synthetic successful model run (fake data, for local dev / screenshots).
dev-seed:
	cd apps/api && poetry run seeing-dev-seed

# API tests against a throwaway Postgres container on port 55434.
test-api:
	@docker run -d --rm --name $(TEST_PG) -e POSTGRES_USER=seeing -e POSTGRES_PASSWORD=seeing \
		-e POSTGRES_DB=seeing_test -p 55434:5432 postgres:16-alpine >/dev/null
	@until docker exec $(TEST_PG) pg_isready -U seeing -d seeing_test -h 127.0.0.1 >/dev/null 2>&1; do sleep 0.5; done
	cd apps/api && poetry run pytest -q; status=$$?; docker stop $(TEST_PG) >/dev/null; exit $$status

test-web:
	cd apps/web && npm run typecheck && npm run lint && npm test

web-image:
	docker build -f apps/api/Dockerfile -t seeing-web:dev .
