# Cloud Run service behind native IAP (no load balancer), request-based billing, scale to zero,
# Direct VPC egress for private ranges only.

data "google_project" "this" {}

locals {
  iap_service_agent = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-iap.iam.gserviceaccount.com"
}

resource "google_cloud_run_v2_service" "this" {
  name     = var.name
  location = var.region

  ingress              = "INGRESS_TRAFFIC_ALL"
  iap_enabled          = true
  invoker_iam_disabled = false
  deletion_protection  = var.deletion_protection

  template {
    service_account                  = var.service_account_email
    max_instance_request_concurrency = var.concurrency
    timeout                          = "60s"

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    vpc_access {
      egress = "PRIVATE_RANGES_ONLY"
      network_interfaces {
        network    = var.network
        subnetwork = var.subnetwork
      }
    }

    containers {
      image = var.image

      ports {
        container_port = var.port
      }

      resources {
        limits = {
          cpu    = var.cpu
          memory = var.memory
        }
        cpu_idle          = true # CPU only allocated during requests (request-based billing)
        startup_cpu_boost = true
      }

      startup_probe {
        http_get {
          path = var.health_path
          port = var.port
        }
        period_seconds    = 3
        timeout_seconds   = 2
        failure_threshold = 20
      }

      dynamic "env" {
        for_each = var.env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = var.secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }
    }
  }

  lifecycle {
    # Images are rolled out by infra/scripts/deploy.sh (gcloud run deploy --image ...).
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
    ]
  }
}

# IAP calls the service as its service agent: it must be an invoker. No allUsers binding.
resource "google_cloud_run_v2_service_iam_member" "iap_invoker" {
  name     = google_cloud_run_v2_service.this.name
  location = var.region
  role     = "roles/run.invoker"
  member   = local.iap_service_agent
}

# Who may pass IAP.
resource "google_iap_web_cloud_run_service_iam_member" "accessors" {
  for_each = toset(var.iap_members)

  cloud_run_service_name = google_cloud_run_v2_service.this.name
  location               = var.region
  role                   = "roles/iap.httpsResourceAccessor"
  member                 = each.value
}
