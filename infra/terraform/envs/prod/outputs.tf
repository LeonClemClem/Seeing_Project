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

output "create_user_job" {
  description = "Cloud Run job running seeing-create-user inside the VPC."
  value       = module.env.create_user_job
}

output "user_password_secret" {
  value = module.env.user_password_secret
}
