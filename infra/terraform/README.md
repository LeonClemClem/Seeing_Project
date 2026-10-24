# Infrastructure (Terraform, GCP `project-astrarome`)

All GCP resources for the seeing forecast site. Names, env vars and topology follow
[`docs/architecture.md`](../../docs/architecture.md). Main goal after correctness: stay inside the
free tiers (target < $10/month for dev + prod together).

## Architecture

```
                         ┌───────────────────── project-astrarome / us-central1 ─────────────────────┐
 browser (owner) ──HTTPS──► Cloud Run service seeing-web-{env}  (IAP enabled natively, no LB;        │
                         │   prod also on seeingthesky.com through a domain mapping)                  │
                         │   SA seeing-web-{env}, min 0 / max 2, 1 vCPU / 512Mi, request billing      │
                         │        │ Direct VPC egress (PRIVATE_RANGES_ONLY)                           │
 Cloud Scheduler ─OAuth──► Cloud Run Admin API jobs/seeing-batch-{env}:run                            │
 (SA seeing-scheduler)   │   Cloud Run job seeing-batch-{env}  ── public internet ──► Météo-France    │
                         │   Cloud Run job seeing-migrate-{env} (web image, `seeing-migrate`)         │
                         │        │ Direct VPC egress                                                 │
                         │  ┌─────▼────────────── VPC seeing-vpc / subnet seeing-us-central1 ───────┐ │
                         │  │ 10.10.0.0/24, Private Google Access, no NAT, no external IPs          │ │
                         │  │   VM seeing-db  e2-micro COS  10.10.0.10  (us-central1-a)             │ │
                         │  │     postgres:16 container (systemd unit from cloud-init)              │ │
                         │  │     boot 10 GB + data disk seeing-db-data 10 GB  ──► daily snapshots  │ │
                         │  │     DBs seeing_dev / seeing_prod (one owner role each)                │ │
                         │  └────────────────▲──────────────────────────────────────────────────────┘ │
 admin laptop ──IAP TCP (35.235.240.0/20, ssh)┘                                                       │
                         │  Artifact Registry: seeing (app images), dockerhub (Docker Hub cache)      │
                         │  Secret Manager: db-password-postgres / -dev / -prod                       │
                         │  Cloud Build (SA seeing-build) → seeing/{web,batch}:<git-sha>              │
 GitHub Actions ──WIF────► SA seeing-deployer-{env} runs infra/scripts/deploy.sh                      │
                         └────────────────────────────────────────────────────────────────────────────┘
```

Terraform roots (each has its own state):

| Root | State | Contents |
|---|---|---|
| `bootstrap/` | **local** (`bootstrap/terraform.tfstate`, gitignored) | APIs, IAP service agent, state bucket `project-astrarome-tfstate` |
| `shared/` | `gs://project-astrarome-tfstate/shared` | VPC + firewall, Artifact Registry repos, DB secrets, DB VM + snapshot schedule, `seeing-scheduler`, `seeing-build` and `seeing-deployer-{dev,prod}` SAs, GitHub Workload Identity pool, Cloud Build source bucket, budget |
| `envs/dev`, `envs/prod` | `.../envs/dev`, `.../envs/prod` | `modules/seeing_env`: SAs `seeing-web-{env}`/`seeing-batch-{env}`, web service (+ prod domain mappings), batch + migrate jobs, Cloud Scheduler job |

Modules: `network`, `db_vm`, `cloud_run_service`, `cloud_run_job`, `scheduled_job`, `seeing_env`
(composition used by both env roots). The two env roots are identical except for the backend
prefix and `terraform.tfvars`.

Provider: `hashicorp/google ~> 8.6.0` (`iap_enabled` on `google_cloud_run_v2_service` and
`google_iap_web_cloud_run_service_iam_member` are GA there), `google-beta` only in bootstrap for
`google_project_service_identity`. Lock files are committed for linux_amd64 / darwin_arm64 /
darwin_amd64.

> **The Terraform state contains secrets** (the generated DB passwords, via `random_password`).
> The state bucket is private (uniform access, public access prevention enforced, versioned).
> Never make it public and never grant `storage.objectViewer` on it to anyone but the owners.

### Security model

- Web: IAP on the Cloud Run service, in both environments. The IAP service agent
  `service-5123733464@gcp-sa-iap.iam.gserviceaccount.com` is the only `roles/run.invoker`; the
  two owners get `roles/iap.httpsResourceAccessor` on the service. No `allUsers`.
- `web_public = true` (not used yet) removes IAP: `allUsers` becomes `roles/run.invoker` and the
  app's own accounts protect what needs protecting.
- GitHub Actions (`seeing-deployer-{dev,prod}`, see [CI/CD](#cicd)): Workload Identity Federation,
  no key. Only `LeonClemClem/Seeing_Project` can get a token, and only on a push to `main` or a
  manual `workflow_dispatch` (pull requests cannot). `seeing-deployer-prod` is reachable from
  `refs/heads/main` only; `seeing-deployer-dev` from any allowed token (the "Deploy to dev" button
  on any branch). Each has `run.developer`, `cloudbuild.builds.editor`, `logging.viewer`, actAs on
  `seeing-build` and on **its own** env's runtime SAs (so dev's cannot deploy prod), admin on the
  build source bucket and read on the `seeing` registry.
- Each Cloud Run SA can read only its own environment's DB password secret. Cloud Run's service
  agent pulls images from same-project Artifact Registry without extra grants; logs are written
  automatically.
- `seeing-scheduler` only has `roles/run.invoker` on the two batch jobs (this role's only
  job-relevant permission is `run.jobs.run`, which is what `jobs/<name>:run` needs).
- DB VM (`seeing-db-vm`): `artifactregistry.reader` on `dockerhub` only, `secretAccessor` on the 3
  DB secrets only, `logging.logWriter`, `monitoring.metricWriter`. No external IP, Shielded VM,
  OS Login, project SSH keys blocked.
- Postgres: firewall + COS host firewall + `pg_hba` allow 5432 from `10.10.0.0/24` only, scram-sha-256,
  role `seeing_<env>` may connect only to database `seeing_<env>` (CONNECT revoked from PUBLIC).
- Cloud Build runs as `seeing-build` (AR writer on `seeing`, log writer, read on the source bucket)
  instead of the Compute default SA (which gets Editor in projects without an organization).

## Expected monthly cost

Prices: us-central1, October 2026. Free tiers are per billing account.

| Resource | Usage | Free tier | Expected |
|---|---|---|---|
| e2-micro `seeing-db` | 730 h | 1 e2-micro in us-central1/us-east1/us-west1 | $0 (≈ $6.1 if the free VM is already used elsewhere on the billing account) |
| pd-standard 10 + 10 GB | 20 GB-month | 30 GB-month | $0 |
| Data disk snapshots, 7 daily, incremental | < 2 GB-month (DB is small) | 5 GB-month in US regions | $0 – 0.10 |
| Cloud Run web (2 envs) | a few hundred requests/day, request-based | 180k vCPU-s, 360k GiB-s, 2M requests | $0 |
| Cloud Run batch jobs (2 vCPU / 4 GiB) | prod 120 + dev 30 runs/month (each downloads ~15 GB; ingress is free) | 240k vCPU-s, 450k GiB-s (instance-based) | 10 min/run: ≈ $0; 20 min/run: ≈ $3; 30 min/run: ≈ $7 |
| Cloud Run migrate jobs | seconds per deploy | (same) | $0 |
| Artifact Registry | ≤ 5 versions × 2 images + postgres cache | 0.5 GB | $0 – 0.20 ($0.10/GB above) |
| Cloud Build | ~5–10 min per image build | 2,500 build-min/month (e2-standard-2) | $0 |
| Secret Manager | 3 active versions, accesses at instance start | 6 versions, 10k accesses | $0 |
| Cloud Scheduler | 2 jobs | 3 jobs | $0 |
| Cloud Storage (state, build sources, us-central1) | < 50 MB | 5 GB-month regional | $0 |
| Logging / Monitoring | ≪ 1 GiB | 50 GiB logs | $0 |
| Networking | no NAT, no LB, no external IP; internet egress to browsers ≪ 1 GB | 1 GB egress | $0 |
| IAP, budgets, IAM | | free | $0 |
| **Total** | | | **≈ $0.5 – 5/month**, dominated by batch runtime |

Batch cost per run ≈ `minutes × 60 × (2 × $0.000018 + 8 × $0.000002)` = $0.0031/minute once the free
tier is exhausted. Lowering `batch_memory` (needs ≥ 2 vCPU above 4 GiB) or the dev frequency are the
main knobs. Budget alerts fire at $10 and $20 actual spend and at $10 forecasted.

## First-time runbook

Prerequisites: Terraform 1.10+, gcloud authenticated as a project owner, plus Application Default
Credentials for Terraform:

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project project-astrarome
```

The budget in `shared/` needs `billing.budgets.create` on billing account `01A1F8-00F06E-B378EB`
(Billing Account Administrator / Costs Manager), i.e. apply `shared/` as Thomas.

All commands below run from `infra/terraform/`.

### 1. Bootstrap (once, local state)

```bash
terraform -chdir=bootstrap init
terraform -chdir=bootstrap apply
```

Enables Run, Compute, Artifact Registry, Secret Manager, Scheduler, IAP, Cloud Build, IAM, CRM,
Billing Budgets, Logging, Monitoring, Storage; provisions the IAP service agent; creates the state
bucket. Keep `bootstrap/terraform.tfstate` somewhere safe (or migrate it: add
`backend "gcs" { bucket = "project-astrarome-tfstate", prefix = "bootstrap" }` and
`terraform init -migrate-state`).

### 2. Shared

```bash
terraform -chdir=shared init
terraform -chdir=shared apply
```

The VM boots, formats the data disk, pulls `postgres:16` through the `dockerhub` remote repo and
creates the roles/databases (first boot ≈ 3–5 min). Check:

```bash
gcloud compute ssh seeing-db --zone us-central1-a --tunnel-through-iap -- \
  'sudo journalctl -u seeing-postgres -n 30 --no-pager; sudo docker exec -u postgres seeing-postgres psql -c "\l"'
```

(`sudo journalctl -u google-startup-scripts`/`cloud-final` show the cloud-init run; look for
`seeing: databases ready`.)

### 3. One-time IAP / OAuth setup in the console (project has no organization)

IAP needs an OAuth brand/client, and Google does not allow creating OAuth clients
programmatically for projects without an organization. Do this once per project (prod reuses it):

1. Console → **Google Auth Platform** (APIs & Services → OAuth consent screen) → **Get started**:
   app name `Seeing`, user support email `thomas.hossler@gmail.com`, **Audience: External**,
   contact email, accept → **Create**.
2. **Audience** page: either add both owners as **Test users** or click **Publish app** (IAP only
   asks for the `openid`/`email` scopes, no verification needed).
3. After step 4 below has created `seeing-web-dev` (or if that apply fails on IAP): Console →
   **Cloud Run** → `seeing-web-dev` → **Security** → *Identity-Aware Proxy (IAP)* → **Edit policy**
   → **Configure in IAP** → **Configure consent screen** if still prompted (audience External) →
   **Auto generate credentials** → **Save**. Back on the service, check IAP is enabled.
   Until this is done, IAP answers every request with `502 Empty Google Account OAuth client
   ID(s)/secret(s)` (it fails closed).
4. If sign-in then fails with **`Error 400: redirect_uri_mismatch`**, the generated client lacks
   IAP's callback. Find the client ID IAP uses (`gcloud iap settings get --project=project-astrarome
   --resource-type=iap_web` doesn't show Cloud Run services; query
   `https://iap.googleapis.com/v1/projects/<number>/iap_web/cloud_run-us-central1/services/seeing-web-dev:iapSettings`),
   then Console → **Google Auth Platform → Clients** → that client (type *Web application*) →
   **Authorized redirect URIs** → add
   `https://iap.googleapis.com/v1/oauth/clientIds/<CLIENT_ID>:handleRedirect` → Save, wait a few
   minutes. For prod, pick the same client in the IAP settings of `seeing-web-prod` so it works
   without further edits.
5. Re-run `terraform -chdir=envs/dev apply`: it should report no changes (or finish the IAP IAM
   bindings that failed before the OAuth client existed).

### 4. Dev environment

```bash
terraform -chdir=envs/dev init
terraform -chdir=envs/dev apply          # then do steps 3.3–3.5 if not done yet
```

This creates the service and jobs with Google's placeholder images (`cloudrun/container/hello`
and `cloudrun/container/job`), so it works before any app image exists.

### 5. Deploy the apps to dev

From the repo root (needs `apps/api/Dockerfile` and `apps/batch/Dockerfile`):

```bash
infra/scripts/deploy.sh dev all
```

Builds `web` and `batch` with Cloud Build (tag = git short SHA), runs `seeing-migrate-dev`
(alembic upgrade head) with the new web image, then deploys `seeing-web-dev` and updates
`seeing-batch-dev`. Terraform ignores image changes, so later `terraform apply` runs don't revert
deployments.

### 6. Run the batch once

```bash
gcloud run jobs execute seeing-batch-dev --region us-central1 --wait
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="seeing-batch-dev"' --limit 50 --freshness 1h
```

### 7. Verify

```bash
terraform -chdir=envs/dev output web_url
curl -sI "$(terraform -chdir=envs/dev output -raw web_url)/healthz"   # 302/401: IAP requires sign-in
```

Open the URL in a browser signed in as an owner: the SPA loads, `/api/runs/latest` returns the run
from step 6. The scheduler job `seeing-batch-dev` can be triggered manually with
`gcloud scheduler jobs run seeing-batch-dev --location us-central1`.

### 7b. Create an admin account

Sign-up on the Compte page only creates `user` accounts. Admin and team accounts are created by the
Cloud Run job `seeing-create-user-{env}` (web image, Direct VPC egress to the DB VM, so no tunnel is
needed). It reads the password from the secret `user-bootstrap-password-{env}`, whose first version
is a random password generated by Terraform.

```bash
# Optional: choose the password instead of the generated one (>= 10 characters).
printf %s 'your-password' | gcloud secrets versions add user-bootstrap-password-dev --data-file=-

gcloud run jobs execute seeing-create-user-dev --region us-central1 --wait \
  --args=--email=you@example.org,--role=admin,--display-name=You
# Change an existing account (password from the secret, role only if given; ends its sessions):
#   --args=--email=you@example.org,--update

gcloud secrets versions access latest --secret=user-bootstrap-password-dev   # the password set
```

Then sign in on the Compte page. `deploy.sh` keeps the job's image in step with `seeing-web-{env}`.
Use one secret version per account you create, and add a fresh version afterwards so the secret no
longer holds a live password.

### 8. Prod

Prod is on `seeingthesky.com` and `www.seeingthesky.com` (`custom_domains` in
`envs/prod/terraform.tfvars`), with Cloud Run domain mappings: no load balancer, Google-managed
certificate. It stays behind IAP (`web_public = false`, same `iap_members` as dev) until the
accounts follow-ups are done. Cloud Run domain mappings are a Preview feature: if IAP sign-in does
not work through the domain, use the `web_url` output (`*.run.app`) meanwhile.

1. Verify the domain once, with the account that runs Terraform: Google Search Console →
   **Add property** → **Domain** `seeingthesky.com` → add the TXT record it gives at the registrar
   → **Verify**.
2. Apply:
   ```bash
   terraform -chdir=envs/prod init
   terraform -chdir=envs/prod apply
   terraform -chdir=envs/prod output domain_dns_records
   ```
3. At the registrar, create the records from that output: A and AAAA records on the apex
   (`seeingthesky.com`) and a CNAME `www` → `ghs.googlehosted.com.`. The certificate is issued
   15 min – a few hours after DNS propagates (`gcloud beta run domain-mappings describe
   --domain seeingthesky.com --region us-central1` shows the status).
4. IAP: Console → Cloud Run → `seeing-web-prod` → Security → IAP → pick the same OAuth client as
   dev (step 3.3). If sign-in on seeingthesky.com fails with `redirect_uri_mismatch`, see step 3.4.
5. Deploy: merge to `main` (see [CI/CD](#cicd)), or by hand `infra/scripts/deploy.sh prod all`
   (same commit as dev: reuses the images). Then fill the DB once:
   `gcloud run jobs execute seeing-batch-prod --region us-central1 --wait`.

## CI/CD

GitHub Actions, in `.github/workflows/`:

| Workflow | When | What |
|---|---|---|
| `ci.yml` (*Tests*) | every pull request | `make test-api`, `test-core`, `test-batch`, `test-web` |
| `deploy-prod.yml` (*Deploy to prod*) | push (merge) to `main` | the tests, then `infra/scripts/deploy.sh prod all` (fails if the new revision does not pass `/healthz`) |
| `deploy-dev.yml` (*Deploy to dev*) | manual: Actions → Deploy to dev → Run workflow → branch | `infra/scripts/deploy.sh dev all` on that branch |

They authenticate with Workload Identity Federation: pool `github`, provider `seeing-project`
and SAs `seeing-deployer-dev` / `seeing-deployer-prod`, all in `shared/`. The provider name and SA e-mail are written in the
workflows (`terraform -chdir=shared output`); they are not secrets. Deploys of the same commit
reuse its image (tag = short SHA), so prod after dev does not rebuild. A failed deploy leaves the
previous revision serving.

Prerequisites: `bootstrap/` applied with `iamcredentials` and `sts` APIs, then `shared/`, then
`envs/*` (they grant `seeing-deployer-<env>` actAs on their runtime SAs).

## Day to day

- **Deploy**: automatic for prod on merge to `main`, button for dev (see [CI/CD](#cicd)). By
  hand: `infra/scripts/deploy.sh <dev|prod> <web|batch|all> [tag]`. Without a tag it builds
  HEAD (only if that tag doesn't exist yet). With a tag it only deploys an existing image.
- **Change infra**: edit, `terraform -chdir=<root> plan`, `apply`. Order when both change:
  `shared` before `envs/*`.
- **Batch sizing / schedule**: `batch_cpu`, `batch_memory`, `batch_timeout_seconds`,
  `batch_schedule` in `envs/<env>/terraform.tfvars`.
- **Cloud-init changes** to the DB VM update the instance metadata in place but only run at the
  next boot: `gcloud compute instances reset seeing-db --zone us-central1-a` (≈ 1 min downtime).
  Passwords and roles are re-synced from Secret Manager on every boot.
- **Rotate a DB password**: `terraform -chdir=shared apply -replace='random_password.db["dev"]'`,
  reset the VM (re-syncs the role password), then redeploy/restart the env
  (`gcloud run services update seeing-web-dev --region us-central1 --update-labels=rotated=$(date +%s)`).

## Connect to the database

From a laptop, the simplest is the IAP TCP tunnel (`iap_tcp_ports = ["22", "5432"]` in
`shared/terraform.tfvars`), which works the same on Windows, macOS and Linux.
`infra/scripts/run_local.py` uses it to run the website locally against the dev DB.

```bash
gcloud compute start-iap-tunnel seeing-db 5432 --local-host-port=localhost:15432 --zone us-central1-a
PGPASSWORD="$(gcloud secrets versions access latest --secret db-password-dev)" \
  psql "host=localhost port=15432 dbname=seeing_dev user=seeing_dev"
```

Other ways:

```bash
# Shell on the VM (OS Login over IAP), then psql inside the container
gcloud compute ssh seeing-db --zone us-central1-a --tunnel-through-iap
sudo docker exec -it -u postgres seeing-postgres psql -d seeing_dev

# Local port-forward through SSH (no extra firewall rule needed)
gcloud compute ssh seeing-db --zone us-central1-a --tunnel-through-iap -- -N -L 15432:127.0.0.1:5432
PGPASSWORD="$(gcloud secrets versions access latest --secret db-password-dev)" \
  psql "host=localhost port=15432 dbname=seeing_dev user=seeing_dev"
```

Opening 5432 to IAP (`iap_tcp_ports`) adds 35.235.240.0/20 to the firewall rule and the host
firewall, and to `pg_hba` for `seeing_dev` only (prod is never reachable from a laptop); after
changing it, apply `shared/` and reset the VM.

## Backups & restore

The data disk has a daily snapshot schedule (`seeing-db-data-daily`, 03:00 UTC, 7-day retention,
stored in us-central1, kept if the disk is deleted). Snapshots are crash-consistent; Postgres
replays its WAL on start. Restore without touching Terraform state:

```bash
gcloud compute snapshots list --filter="sourceDisk~seeing-db-data"
gcloud compute disks create seeing-db-restore --zone us-central1-a --source-snapshot <SNAPSHOT>
gcloud compute instances attach-disk seeing-db --zone us-central1-a --disk seeing-db-restore --device-name restore
gcloud compute ssh seeing-db --zone us-central1-a --tunnel-through-iap -- '
  sudo systemctl stop seeing-postgres &&
  sudo mkdir -p /mnt/disks/restore && sudo mount /dev/disk/by-id/google-restore /mnt/disks/restore &&
  sudo rsync -a --delete /mnt/disks/restore/pgdata/ /mnt/disks/pgdata/pgdata/ &&
  sudo umount /mnt/disks/restore && sudo systemctl start seeing-postgres'
gcloud compute instances detach-disk seeing-db --zone us-central1-a --disk seeing-db-restore
gcloud compute disks delete seeing-db-restore --zone us-central1-a
```

## Roll back

- **App**: redeploy the previous image: `infra/scripts/deploy.sh prod web <previous-sha>` (list
  tags with `gcloud artifacts docker images list us-central1-docker.pkg.dev/project-astrarome/seeing/web --include-tags`).
  Instant alternative for the web service: `gcloud run services update-traffic seeing-web-prod
  --region us-central1 --to-revisions <REVISION>=100` (then `--to-latest` after the next good deploy).
  Migrations are not rolled back: keep them backward compatible (expand, then contract).
- **Infra**: revert the commit and `terraform apply` the affected root.

## Destroy

- **dev**: `terraform -chdir=envs/dev destroy` (deletion protection is off in dev). The
  `seeing_dev` database stays on the VM; drop it manually if wanted.
- **prod**: set `deletion_protection = false` in `envs/prod/terraform.tfvars`, `apply`, then
  `destroy`.
- **shared** (only after both envs): the data disk has `prevent_destroy`, so `destroy` stops on
  it on purpose. To really delete everything, remove that lifecycle block in `modules/db_vm`,
  destroy, then delete leftover snapshots (`KEEP_AUTO_SNAPSHOTS`) by hand. APIs stay enabled and
  the state bucket is protected (`prevent_destroy`) in `bootstrap/`.

## Notes / known caveats

- If `gcloud run deploy` starts setting other fields that Terraform then wants to revert, add
  them to `ignore_changes` in `modules/cloud_run_service` / `modules/cloud_run_job`.
- Cloud Run Direct VPC egress uses addresses of `10.10.0.0/24` (plenty for max 2 web instances +
  jobs); the Postgres firewall rule allows the whole subnet.
- The DB VM has 1 GB RAM: Postgres is tuned for it (`shared_buffers=128MB`,
  `effective_cache_size=384MB`, `max_connections=40`, `work_mem=4MB`); keep app pools small
  (e.g. pool_size 5 per instance).
- Scheduler times are UTC; the AROME availability (and so the cron) is to be confirmed by the batch
  owner (`batch_schedule` var).
