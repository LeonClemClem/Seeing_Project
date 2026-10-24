output "web_url" {
  value = module.web.uri
}

output "web_service" {
  value = module.web.name
}

output "batch_job" {
  value = module.batch.name
}

output "migrate_job" {
  value = module.migrate.name
}

output "create_user_job" {
  value = module.create_user.name
}

output "user_password_secret" {
  description = "Secret holding the password seeing-create-user-<env> sets."
  value       = google_secret_manager_secret.user_password.secret_id
}

output "web_service_account" {
  value = google_service_account.web.email
}

output "batch_service_account" {
  value = google_service_account.batch.email
}

output "domain_dns_records" {
  value = module.web.domain_dns_records
}
