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
