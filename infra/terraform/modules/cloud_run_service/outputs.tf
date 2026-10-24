output "name" {
  value = google_cloud_run_v2_service.this.name
}

output "uri" {
  value = google_cloud_run_v2_service.this.uri
}

output "domain_dns_records" {
  description = "Per custom domain, the DNS records to create at the registrar."
  value = {
    for domain, mapping in google_cloud_run_domain_mapping.this : domain => [
      for record in try(mapping.status[0].resource_records, []) : {
        type   = record.type
        name   = record.name
        rrdata = record.rrdata
      }
    ]
  }
}
