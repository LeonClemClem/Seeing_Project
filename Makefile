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
