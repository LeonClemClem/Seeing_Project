# Thin root: shared outputs + one call of the environment module. envs/prod/main.tf is identical
# apart from the backend prefix in versions.tf; differences live in terraform.tfvars.

data "terraform_remote_state" "shared" {
  backend = "gcs"
  config = {
    bucket = "project-astrarome-tfstate"
    prefix = "shared"
  }
}

locals {
  shared = data.terraform_remote_state.shared.outputs
}

module "env" {
  source = "../../modules/seeing_env"

  env                             = var.env
  region                          = local.shared.region
  network_id                      = local.shared.network_id
  subnet_id                       = local.shared.subnet_id
  db_host                         = local.shared.db_host
  db_port                         = local.shared.db_port
  db_password_secret_id           = local.shared.db_password_secret_ids[var.env]
  scheduler_service_account_email = local.shared.scheduler_service_account_email
  deployer_service_account_email  = local.shared.deployer_service_account_email
  iap_members                     = var.iap_members
  web_public                      = var.web_public
  custom_domains                  = var.custom_domains

  web_image         = var.web_image
  job_image         = var.job_image
  web_max_instances = var.web_max_instances

  batch_cpu             = var.batch_cpu
  batch_memory          = var.batch_memory
  batch_timeout_seconds = var.batch_timeout_seconds
  batch_max_retries     = var.batch_max_retries
  batch_env             = var.batch_env
  batch_schedule        = var.batch_schedule

  deletion_protection = var.deletion_protection
}
