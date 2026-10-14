# Architecture & contracts

This document is the contract between the parts of the mono repo. Change it (and the code on both
sides) together.

## Overview

```
Cloud Scheduler ──► Cloud Run Job  seeing-batch-{env}   download AROME → compute sites → write DB
                        │  Direct VPC egress (private IP)
                        ▼
   e2-micro VM "seeing-db" (COS, postgres:16 container, no public IP)  DBs: seeing_dev, seeing_prod
                        ▲
Cloud Run Service seeing-web-{env}   FastAPI: /api/* + built React SPA   ◄── IAP (project owners)
```

- GCP project `project-astrarome`, region **`us-central1`** (always-free e2-micro for the DB VM).
- Two environments, `dev` and `prod`, in the same project: one shared VPC and DB VM, with separate
  databases, Cloud Run resources, service accounts and secrets per environment.

## Repo layout

| Path | What | Owner |
|---|---|---|
| `research/` | Original scripts, papers, Poetry env for experiments. Not imported by the apps. | friend |
| `packages/seeing_core/` | Pure seeing computation refactored from `research/SeeingAromeV2_correction_conv_tke.py`. | core |
| `packages/seeing_db/` | SQLAlchemy models + Alembic migrations (incl. site seed). Shared by batch and api. | shared |
| `apps/batch/` | Cloud Run Job: download AROME, run `seeing_core`, persist via `seeing_db`. | core |
| `apps/api/` | FastAPI app; serves `/api/*` and the built SPA. | web |
| `apps/web/` | React + Vite + TypeScript SPA (MapLibre, ECharts). | web |
| `infra/terraform/` | All GCP resources. | infra |

Python 3.12 everywhere, Poetry 1.8 with path dependencies (`packages/*` are depended on with
`{path = "../../packages/<name>", develop = true}`). Docker builds use the **repo root** as
context so path dependencies resolve.

## Database (`packages/seeing_db`)

Postgres 16. Schema is defined by the SQLAlchemy models in `packages/seeing_db/seeing_db/models.py`
and created by Alembic (`packages/seeing_db/seeing_db/migrations`). Tables:

- `sites(id, slug UNIQUE, name, lat, lon, altitude_m NULL, k_tke_conv, k_tke, k_cis, active, created_at)`
- `model_runs(id, run_time UNIQUE (AROME cycle, UTC), status ∈ {running, success, failed},
  started_at, finished_at NULL, error NULL)`
- `forecasts(id, run_id → model_runs ON DELETE CASCADE, site_id → sites, valid_time, lead_hour,
  seeing_arcsec NULL, r0_m NULL, integral_cn2 NULL, h_coulim_m NULL, model_altitude_m NULL,
  UNIQUE(run_id, site_id, lead_hour))`
- `cn2_profiles(id, run_id → model_runs ON DELETE CASCADE, site_id → sites, valid_time, lead_hour,
  heights_m REAL[], cn2 REAL[], UNIQUE(run_id, site_id, lead_hour))`. `heights_m` are metres above
  ground level, on a regular display grid (100 m steps up to the top of the profile).

Rules:
- The batch job writes a run as `running`, inserts all rows, then flips to `success` in one
  transaction per run (re-running the same `run_time` replaces its rows: idempotent).
- The API only ever reads runs with `status = 'success'`. "Latest" = max `run_time` with success.
- Retention: the batch deletes runs older than `RETENTION_DAYS` (default 14) after a success.
- NaN values are stored as SQL NULL.

## Configuration (env vars)

Shared DB connection (both apps), resolved by `seeing_db.config.database_url()`:

| Var | Meaning |
|---|---|
| `DATABASE_URL` | Full SQLAlchemy URL; if set, wins (local dev). e.g. `postgresql+psycopg://seeing:seeing@localhost:5432/seeing_dev` |
| `DB_HOST`, `DB_PORT` (5432), `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Used on Cloud Run. `DB_PASSWORD` is injected from Secret Manager. |

Batch only:

| Var | Default | Meaning |
|---|---|---|
| `GRIB_DIR` | `/tmp/arome` | Scratch folder for downloaded GRIB2 (Cloud Run: in-memory FS). |
| `FORECAST_HOURS` | `51` | Last lead hour computed (0..51). |
| `RETENTION_DAYS` | `14` | Model runs older than this are deleted. |
| `LOG_LEVEL` | `INFO` | |

API only: `PORT` (8080, set by Cloud Run), `STATIC_DIR` (`/app/static`, built SPA), `ENV`
(`dev`/`prod`, shown in the UI header).

## seeing_core interface

```python
@dataclass(frozen=True)
class SiteSpec:
    slug: str; lat: float; lon: float
    k_tke_conv: float; k_tke: float; k_cis: float

@dataclass
class HourResult:
    lead_hour: int; valid_time: datetime            # tz-aware UTC
    seeing_arcsec: float; r0_m: float; integral_cn2: float
    h_coulim_m: float; model_altitude_m: float
    heights_m: np.ndarray; cn2: np.ndarray          # display grid profile (AGL)

@dataclass
class SiteForecast:
    slug: str; run_time: datetime; hours: list[HourResult]

def compute_sites(grib_dir: Path, sites: Sequence[SiteSpec],
                  forecast_hours: int = 51) -> dict[str, SiteForecast]: ...
```

All sites are extracted in a **single pass** over each GRIB file. No globals, no matplotlib in
the computation path; numerical results must match the V2 script for the same inputs.

## Batch CLI (`apps/batch`, console script `seeing-batch`)

- `seeing-batch run [--run-time 2026-10-13T00:00Z] [--keep-gribs]`: default run time is the
  latest AROME cycle with all packages and hours available (`Arome0025.get_latest_forecast_time` /
  `get_forecast(date=...)`). Packages: `SP2 SP3 HP1 HP2 IP1 IP4`. Exits 0 when the run was stored
  (or already stored as success), non-zero otherwise.
- Downloads and processes one package at a time where possible, deleting GRIBs afterwards, so
  peak disk (= RAM on Cloud Run) stays bounded.

## API (`apps/api`)

All responses are JSON; times are ISO 8601 UTC (`Z`).

- `GET /healthz` → `{"status": "ok"}` (no DB access).
- `GET /api/sites` → `[{slug, name, lat, lon, altitude_m}]` (active sites only).
- `GET /api/runs/latest` → `{run_time, finished_at, status}` or 404 when no successful run.
- `GET /api/sites/{slug}/forecast?run=latest|<ISO run_time>` →
  `{site: {...}, run_time, points: [{lead_hour, valid_time, seeing_arcsec, r0_m, integral_cn2, h_coulim_m}]}`
- `GET /api/sites/{slug}/cn2?run=latest|<ISO run_time>` →
  `{site: {...}, run_time, valid_times: [...], heights_m: [...], cn2: [[...per height...] per valid_time]}`
  (`null` for missing values; heights are the union grid, padded with null).
- Unknown slug or run → 404.
- Everything else not under `/api` serves the SPA (`index.html` fallback for client routes).

Auth: none in the app. IAP sits in front of the Cloud Run service; the app can read
`X-Goog-Authenticated-User-Email` for display only.

## Containers

Registry: `us-central1-docker.pkg.dev/project-astrarome/seeing/<image>:<git-sha>`.

| Image | Dockerfile | Entrypoint | Used by |
|---|---|---|---|
| `web` | `apps/api/Dockerfile` (multi-stage: node builds `apps/web`, python runs FastAPI) | `uvicorn seeing_api.main:app --host 0.0.0.0 --port $PORT`; also contains `alembic` (`seeing-migrate` = `alembic upgrade head`) | `seeing-web-{env}` service, `seeing-migrate-{env}` job |
| `batch` | `apps/batch/Dockerfile` | `seeing-batch run` | `seeing-batch-{env}` job |

## Infra names

| Resource | Name |
|---|---|
| Terraform state bucket | `project-astrarome-tfstate` (prefixes `shared`, `envs/dev`, `envs/prod`) |
| VPC / subnet | `seeing-vpc` / `seeing-us-central1` `10.10.0.0/24`, Private Google Access on |
| DB VM | `seeing-db`, e2-micro, COS, internal IP `10.10.0.10`, data disk `seeing-db-data` (10 GB pd-standard) |
| Artifact Registry | `seeing` (docker), `dockerhub` (remote repo proxying Docker Hub, for the postgres image) |
| Secrets | `db-password-postgres`, `db-password-dev`, `db-password-prod` |
| DB / user per env | `seeing_dev` / `seeing_dev`, `seeing_prod` / `seeing_prod` |
| Service accounts | `seeing-web-{env}`, `seeing-batch-{env}`, `seeing-db-vm`, `seeing-scheduler` |
| Cloud Run | `seeing-web-{env}` (service), `seeing-batch-{env}`, `seeing-migrate-{env}` (jobs) |
| Backups bucket | `project-astrarome-seeing-backups` |
| Scheduler | `seeing-batch-prod` (4×/day, after the 00/06/12/18 UTC AROME cycles are published), `seeing-batch-dev` (1×/day) |
