output "web_url" {
  description = "IAP-protected URL of the web service."
  value       = module.env.web_url
}

output "web_service" {
  value = module.env.web_service
}

output "batch_job" {
  value = module.env.batch_job
}

output "migrate_job" {
  value = module.env.migrate_job
}
