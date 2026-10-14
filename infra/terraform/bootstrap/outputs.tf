output "state_bucket" {
  value = google_storage_bucket.tfstate.name
}

output "iap_service_agent" {
  value = google_project_service_identity.iap.email
}
