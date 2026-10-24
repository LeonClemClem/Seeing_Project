# Consumed by envs/* through terraform_remote_state (prefix "shared").

output "project_id" {
  value = var.project_id
}

output "project_number" {
  value = data.google_project.this.number
}

output "region" {
  value = var.region
}

output "network_id" {
  value = module.network.network_id
}

output "subnet_id" {
  value = module.network.subnet_id
}

output "db_host" {
  value = module.db_vm.internal_ip
}

output "db_port" {
  value = 5432
}

output "db_password_secret_ids" {
  description = "env => Secret Manager secret id of that environment's DB password."
  value       = { for env in var.environments : env => google_secret_manager_secret.db[env].secret_id }
}

output "registry_url" {
  description = "Docker repository for application images."
  value       = "${local.registry_host}/${var.project_id}/${google_artifact_registry_repository.seeing.repository_id}"
}

output "scheduler_service_account_email" {
  value = google_service_account.scheduler.email
}

output "build_service_account_email" {
  value = google_service_account.build.email
}

output "build_source_bucket" {
  value = google_storage_bucket.build_source.name
}

output "deployer_service_account_emails" {
  description = "env => SA used by GitHub Actions (service_account in .github/workflows/deploy-<env>.yml)."
  value       = { for env, sa in google_service_account.deployer : env => sa.email }
}

output "github_workload_identity_provider" {
  description = "workload_identity_provider in .github/workflows/deploy-*.yml."
  value       = google_iam_workload_identity_pool_provider.github.name
}
