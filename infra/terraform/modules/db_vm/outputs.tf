output "internal_ip" {
  value = google_compute_address.internal.address
}

output "instance_name" {
  value = google_compute_instance.db.name
}

output "service_account_email" {
  value = google_service_account.vm.email
}

output "data_disk_name" {
  value = google_compute_disk.data.name
}
