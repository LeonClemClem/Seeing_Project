output "web_url" {
  description = "Cloud Run URL of the web service (IAP-protected unless web_public)."
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

output "domain_dns_records" {
  description = "DNS records to create at the registrar for each custom domain."
  value       = module.env.domain_dns_records
}
