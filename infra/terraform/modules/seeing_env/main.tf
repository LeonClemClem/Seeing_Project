# Everything one environment (dev or prod) owns: service accounts, the web service, the batch and
# migrate jobs and the batch schedule. Shared pieces (VPC, DB VM, secrets, registry, scheduler SA)
# come in as inputs from the `shared` root.

locals {
  db_name = "seeing_${var.env}"

  db_env = {
    DB_HOST = var.db_host
    DB_PORT = tostring(var.db_port)
    DB_NAME = local.db_name
    DB_USER = local.db_name
    ENV     = var.env
  }
  db_secret_env = { DB_PASSWORD = var.db_password_secret_id }
}

# --- Service accounts: each one can read only this environment's DB password -------------------

resource "google_service_account" "web" {
  account_id   = "seeing-web-${var.env}"
  display_name = "Seeing web (${var.env})"
}

resource "google_service_account" "batch" {
  account_id   = "seeing-batch-${var.env}"
  display_name = "Seeing batch (${var.env})"
}

resource "google_secret_manager_secret_iam_member" "db_password" {
  for_each = {
    web   = google_service_account.web.member
    batch = google_service_account.batch.member
  }

  secret_id = var.db_password_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = each.value
}

# deploy.sh (GitHub Actions, seeing-deployer-<env>) deploys the service and jobs, which run as these SAs.
resource "google_service_account_iam_member" "deployer_acts_as" {
  for_each = {
    web   = google_service_account.web.name
    batch = google_service_account.batch.name
  }

  service_account_id = each.value
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${var.deployer_service_account_email}"
}

# --- Web service + migrations job (same image) --------------------------------------------------

module "web" {
  source = "../cloud_run_service"

  name                  = "seeing-web-${var.env}"
  region                = var.region
  image                 = var.web_image
  service_account_email = google_service_account.web.email
  network               = var.network_id
  subnetwork            = var.subnet_id
  cpu                   = "1"
  memory                = "512Mi"
  min_instances         = 0
  max_instances         = var.web_max_instances
  env                   = local.db_env
  secret_env            = local.db_secret_env
  iap_members           = var.iap_members
  public                = var.web_public
  custom_domains        = var.custom_domains
  deletion_protection   = var.deletion_protection

  depends_on = [google_secret_manager_secret_iam_member.db_password]
}

module "migrate" {
  source = "../cloud_run_job"

  name                  = "seeing-migrate-${var.env}"
  region                = var.region
  image                 = var.job_image
  command               = ["seeing-migrate"]
  service_account_email = google_service_account.web.email
  network               = var.network_id
  subnetwork            = var.subnet_id
  cpu                   = "1"
  memory                = "512Mi"
  timeout_seconds       = 600
  max_retries           = 0
  env                   = local.db_env
  secret_env            = local.db_secret_env
  deletion_protection   = var.deletion_protection

  depends_on = [google_secret_manager_secret_iam_member.db_password]
}

# --- Account administration: seeing-create-user inside the VPC ----------------------------------
# Sign-up only creates `user` accounts. This job (same image as the web service, Direct VPC egress to
# the DB VM) creates admin/team accounts. Its password comes from a Secret Manager secret whose
# first version is a random bootstrap password; add a new version to choose another one. See
# infra/terraform/README.md, "Create an admin account".
# NOTE: the random_password result is stored in the Terraform state (private bucket).

resource "random_password" "user_bootstrap" {
  length  = 24
  special = false
}

resource "google_secret_manager_secret" "user_password" {
  secret_id = "user-bootstrap-password-${var.env}"
  labels    = { app = "seeing" }

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret_version" "user_password" {
  secret      = google_secret_manager_secret.user_password.id
  secret_data = random_password.user_bootstrap.result

  lifecycle {
    # Later versions are added by hand (gcloud secrets versions add); never roll them back.
    ignore_changes = [secret_data]
  }
}

resource "google_secret_manager_secret_iam_member" "user_password" {
  secret_id = google_secret_manager_secret.user_password.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.web.member
}

module "create_user" {
  source = "../cloud_run_job"

  name                  = "seeing-create-user-${var.env}"
  region                = var.region
  image                 = var.job_image
  command               = ["seeing-create-user"]
  service_account_email = google_service_account.web.email
  network               = var.network_id
  subnetwork            = var.subnet_id
  cpu                   = "1"
  memory                = "512Mi"
  timeout_seconds       = 120
  max_retries           = 0
  env                   = local.db_env
  secret_env            = merge(local.db_secret_env, { SEEING_USER_PASSWORD = google_secret_manager_secret.user_password.secret_id })
  deletion_protection   = var.deletion_protection

  depends_on = [
    google_secret_manager_secret_iam_member.db_password,
    google_secret_manager_secret_iam_member.user_password,
    google_secret_manager_secret_version.user_password,
  ]
}

# --- Batch job + schedule -------------------------------------------------------------------------

module "batch" {
  source = "../cloud_run_job"

  name                  = "seeing-batch-${var.env}"
  region                = var.region
  image                 = var.job_image
  service_account_email = google_service_account.batch.email
  network               = var.network_id
  subnetwork            = var.subnet_id
  cpu                   = var.batch_cpu
  memory                = var.batch_memory
  timeout_seconds       = var.batch_timeout_seconds
  max_retries           = var.batch_max_retries
  env                   = merge(var.batch_env, local.db_env)
  secret_env            = local.db_secret_env
  deletion_protection   = var.deletion_protection

  depends_on = [google_secret_manager_secret_iam_member.db_password]
}

module "batch_schedule" {
  source = "../scheduled_job"

  name                            = "seeing-batch-${var.env}"
  region                          = var.region
  job_name                        = module.batch.name
  schedule                        = var.batch_schedule
  scheduler_service_account_email = var.scheduler_service_account_email
}
