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

output "web_service_account" {
  value = google_service_account.web.email
}

output "batch_service_account" {
  value = google_service_account.batch.email
}
