# Resources shared by dev and prod: network, registry, DB VM + passwords, scheduler and build
# service accounts, budget alerts.

data "google_project" "this" {}

locals {
  registry_host = "${var.region}-docker.pkg.dev"
  # env => secret id; the env roots read these through terraform_remote_state.
  db_secret_ids = { for env in var.environments : env => "db-password-${env}" }
}

# --- Network ------------------------------------------------------------------------------------

module "network" {
  source = "../modules/network"

  region        = var.region
  network_name  = "seeing-vpc"
  subnet_name   = "seeing-us-central1"
  subnet_cidr   = var.subnet_cidr
  db_target_tag = "seeing-db"
  iap_tcp_ports = var.iap_tcp_ports
}

# --- Artifact Registry (stay under the 0.5 GB free storage) -------------------------------------

resource "google_artifact_registry_repository" "seeing" {
  repository_id = "seeing"
  location      = var.region
  format        = "DOCKER"
  description   = "Application images (web, batch)"

  cleanup_policy_dry_run = false

  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = var.registry_keep_versions
    }
  }

  cleanup_policies {
    id     = "delete-untagged"
    action = "DELETE"
    condition {
      tag_state  = "UNTAGGED"
      older_than = "604800s" # 7 days
    }
  }

  cleanup_policies {
    id     = "delete-old"
    action = "DELETE"
    condition {
      tag_state  = "ANY"
      older_than = "1209600s" # 14 days (the keep-recent policy wins over this one)
    }
  }
}

resource "google_artifact_registry_repository" "dockerhub" {
  repository_id = "dockerhub"
  location      = var.region
  format        = "DOCKER"
  mode          = "REMOTE_REPOSITORY"
  description   = "Docker Hub pull-through cache (postgres image for the DB VM)"

  remote_repository_config {
    description = "Docker Hub"
    docker_repository {
      public_repository = "DOCKER_HUB"
    }
  }

  cleanup_policy_dry_run = false

  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 2
    }
  }

  cleanup_policies {
    id     = "delete-old"
    action = "DELETE"
    condition {
      tag_state  = "ANY"
      older_than = "2592000s" # 30 days; re-fetched from Docker Hub on demand
    }
  }
}

# --- DB passwords (alphanumeric: safe in URLs and in the VM's psql bootstrap) -------------------
# NOTE: random_password results are stored in the Terraform state => the state bucket is private.

resource "random_password" "db" {
  for_each = toset(concat(["postgres"], var.environments))

  length  = 32
  special = false
}

resource "google_secret_manager_secret" "db" {
  for_each = random_password.db

  secret_id = "db-password-${each.key}"
  labels    = { app = "seeing" }

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret_version" "db" {
  for_each = random_password.db

  secret      = google_secret_manager_secret.db[each.key].id
  secret_data = each.value.result
}

# --- DB VM --------------------------------------------------------------------------------------

module "db_vm" {
  source = "../modules/db_vm"

  project_id          = var.project_id
  name                = "seeing-db"
  region              = var.region
  zone                = var.zone
  subnet_id           = module.network.subnet_id
  internal_ip         = var.db_internal_ip
  network_tag         = "seeing-db"
  postgres_image      = "${local.registry_host}/${var.project_id}/${google_artifact_registry_repository.dockerhub.repository_id}/library/postgres:16"
  image_repository_id = google_artifact_registry_repository.dockerhub.repository_id
  superuser_secret_id = google_secret_manager_secret.db["postgres"].secret_id
  databases = {
    for env in var.environments : "seeing_${env}" => google_secret_manager_secret.db[env].secret_id
  }
  client_cidrs = [var.subnet_cidr]
  # Adding "5432" to iap_tcp_ports lets `gcloud compute start-iap-tunnel` reach Postgres, for the
  # dev database only (laptops never need prod).
  db_client_cidrs = contains(var.iap_tcp_ports, "5432") ? { seeing_dev = ["35.235.240.0/20"] } : {}

  depends_on = [google_secret_manager_secret_version.db]
}

# --- Service accounts used across environments --------------------------------------------------

# Cloud Scheduler calls the Cloud Run Admin API as this SA; envs grant it run.invoker per job.
resource "google_service_account" "scheduler" {
  account_id   = "seeing-scheduler"
  display_name = "Seeing Cloud Scheduler"
}

# Cloud Build runs as this SA (instead of the over-privileged Compute default SA).
resource "google_service_account" "build" {
  account_id   = "seeing-build"
  display_name = "Seeing Cloud Build"
}

resource "google_project_iam_member" "build_logs" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = google_service_account.build.member
}

resource "google_artifact_registry_repository_iam_member" "build_push" {
  location   = var.region
  repository = google_artifact_registry_repository.seeing.repository_id
  role       = "roles/artifactregistry.writer"
  member     = google_service_account.build.member
}

# Regional bucket for `gcloud builds submit` source tarballs (instead of the default US
# multi-region <project>_cloudbuild bucket, which is outside the free tier).
resource "google_storage_bucket" "build_source" {
  name                        = "${var.project_id}-cloudbuild-src"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true

  soft_delete_policy {
    retention_duration_seconds = 0
  }

  lifecycle_rule {
    condition {
      age = 7
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_storage_bucket_iam_member" "build_source" {
  bucket = google_storage_bucket.build_source.name
  role   = "roles/storage.objectViewer"
  member = google_service_account.build.member
}

# --- GitHub Actions deployers (Workload Identity Federation, no keys) ---------------------------
# .github/workflows/deploy-{prod,dev}.yml exchange GitHub's OIDC token for seeing-deployer-<env>
# and run infra/scripts/deploy.sh. Only this repository can get a token, and only for pushes to
# main or a manual "Run workflow": pull requests, including from forks, never can. The prod
# deployer is reachable from main only, so any branch can go to dev but only reviewed code to prod.

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "seeing-project"
  display_name                       = "Seeing_Project repository"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
    "attribute.event_name" = "assertion.event_name"
    "attribute.main"       = "assertion.ref == 'refs/heads/main' ? 'true' : 'false'"
  }
  attribute_condition = <<-EOT
    assertion.repository == "${var.github_repository}" &&
    (assertion.ref == "refs/heads/main" || assertion.event_name == "workflow_dispatch")
  EOT

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

locals {
  pool_principals = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}"
  # env => who may impersonate its deployer: prod only from main, dev from any allowed token.
  deployer_principals = {
    for env in var.environments : env => (
      env == "prod" ? "${local.pool_principals}/attribute.main/true" : "${local.pool_principals}/attribute.repository/${var.github_repository}"
    )
  }
  # (env, role) pairs for the project-level roles below.
  deployer_project_roles = {
    for pair in setproduct(var.environments, [
      "roles/run.developer",
      "roles/logging.viewer",
      "roles/cloudbuild.builds.editor",
      "roles/serviceusage.serviceUsageConsumer",
    ]) : "${pair[0]} ${pair[1]}" => { env = pair[0], role = pair[1] }
  }
}

resource "google_service_account" "deployer" {
  for_each = toset(var.environments)

  account_id   = "seeing-deployer-${each.value}"
  display_name = "Seeing deployer ${each.value} (GitHub Actions)"
}

resource "google_service_account_iam_member" "deployer_wif" {
  for_each = local.deployer_principals

  service_account_id = google_service_account.deployer[each.key].name
  role               = "roles/iam.workloadIdentityUser"
  member             = each.value
}

# Deploy Cloud Run services/jobs and execute the migrate job; read build logs (CLOUD_LOGGING_ONLY
# builds stream from Cloud Logging); submit builds. The env roots grant actAs on their runtime SAs.
# A deployer cannot deploy the other env's service or jobs: that needs actAs on its runtime SAs.
resource "google_project_iam_member" "deployer" {
  for_each = local.deployer_project_roles

  project = var.project_id
  role    = each.value.role
  member  = google_service_account.deployer[each.value.env].member
}

# `gcloud builds submit --service-account=seeing-build` needs actAs on the build SA.
resource "google_service_account_iam_member" "deployer_acts_as_build" {
  for_each = google_service_account.deployer

  service_account_id = google_service_account.build.name
  role               = "roles/iam.serviceAccountUser"
  member             = each.value.member
}

# Upload source tarballs (bucket-scoped admin: gcloud also reads the bucket's metadata).
resource "google_storage_bucket_iam_member" "deployer_source" {
  for_each = google_service_account.deployer

  bucket = google_storage_bucket.build_source.name
  role   = "roles/storage.admin"
  member = each.value.member
}

# deploy.sh checks whether an image tag already exists before building.
resource "google_artifact_registry_repository_iam_member" "deployer_read" {
  for_each = google_service_account.deployer

  location   = var.region
  repository = google_artifact_registry_repository.seeing.repository_id
  role       = "roles/artifactregistry.reader"
  member     = each.value.member
}

# --- Budget alerts ------------------------------------------------------------------------------
# One budget of $10 with alerts at 100% ($10) and 200% ($20) of actual spend, plus 100% of
# forecasted spend. Emails go to billing account admins/users (default IAM recipients), to the
# project owners (project-level recipients) and to the e-mail notification channels below.

resource "google_monitoring_notification_channel" "budget_email" {
  for_each = toset(var.alert_emails)

  display_name = "Budget alerts ${each.value}"
  type         = "email"
  labels = {
    email_address = each.value
  }
}

resource "google_billing_budget" "project" {
  billing_account = var.billing_account
  display_name    = "${var.project_id} monthly"

  budget_filter {
    projects               = ["projects/${data.google_project.this.number}"]
    calendar_period        = "MONTH"
    credit_types_treatment = "INCLUDE_ALL_CREDITS"
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.budget_amount_usd)
    }
  }

  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "CURRENT_SPEND"
  }

  threshold_rules {
    threshold_percent = 2.0
    spend_basis       = "CURRENT_SPEND"
  }

  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "FORECASTED_SPEND"
  }

  all_updates_rule {
    disable_default_iam_recipients   = false
    enable_project_level_recipients  = true
    monitoring_notification_channels = [for c in google_monitoring_notification_channel.budget_email : c.id]
  }
}
