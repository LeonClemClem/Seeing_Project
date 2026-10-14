# Cloud Run job (batch or one-off task) with Direct VPC egress for private ranges only; public
# traffic (e.g. Météo-France downloads) leaves directly from Cloud Run, so no Cloud NAT is needed.

resource "google_cloud_run_v2_job" "this" {
  name                = var.name
  location            = var.region
  deletion_protection = var.deletion_protection

  template {
    task_count  = 1
    parallelism = 1

    template {
      service_account       = var.service_account_email
      max_retries           = var.max_retries
      timeout               = "${var.timeout_seconds}s"
      execution_environment = "EXECUTION_ENVIRONMENT_GEN2"

      vpc_access {
        egress = "PRIVATE_RANGES_ONLY"
        network_interfaces {
          network    = var.network
          subnetwork = var.subnetwork
        }
      }

      containers {
        image   = var.image
        command = var.command
        args    = var.args

        resources {
          limits = {
            cpu    = var.cpu
            memory = var.memory
          }
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
  }

  lifecycle {
    # Images are rolled out by infra/scripts/deploy.sh (gcloud run jobs update --image ...).
    ignore_changes = [
      template[0].template[0].containers[0].image,
      client,
      client_version,
    ]
  }
}
