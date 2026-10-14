# Seeing Project

Forecasts of astronomical **seeing** (optical turbulence, in arcseconds) for observing sites in
France, computed from Météo-France's AROME weather model and published on a website.

| Path | What |
|---|---|
| [`research/`](research/README.md) | The original research scripts and papers. Experiment here. |
| `packages/seeing_core/` | The seeing computation, packaged for the batch job. |
| `packages/seeing_db/` | Database models and migrations. |
| `apps/batch/` | Scheduled job: downloads each AROME run and computes forecasts for every site. |
| `apps/api/` | FastAPI backend that also serves the website. |
| `apps/web/` | React frontend. |
| `infra/terraform/` | Google Cloud infrastructure (project `project-astrarome`). |

How the pieces fit together, and the contracts between them: [docs/architecture.md](docs/architecture.md).

## Local development

Requirements: Python 3.12, Poetry, Node 20+, Docker.

```bash
make db-up      # local Postgres on :5432
make migrate    # create tables + seed sites
```

### Website (API + SPA)

```bash
make api-install web-install
make dev-seed   # synthetic forecast run (fake data) until the batch job has filled the DB
make api-dev    # FastAPI on http://localhost:8000 (API docs at /api/docs)
make web-dev    # Vite on http://localhost:5173, proxies /api to :8000
make test-api   # pytest against a throwaway Postgres on :55434
make test-web   # typecheck + eslint + vitest
make web-image  # production image (apps/api/Dockerfile, repo root as context)
```

Seeing thresholds and colours live in `apps/web/src/config.ts`.
