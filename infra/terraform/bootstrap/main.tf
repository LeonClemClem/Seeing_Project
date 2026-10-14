# Bootstrap: applied once by a human with local state.
# Enables the APIs every other root needs and creates the remote state bucket.

terraform {
  required_version = ">= 1.10.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.6.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 8.6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

locals {
  services = toset([
    "artifactregistry.googleapis.com",
    "billingbudgets.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "cloudscheduler.googleapis.com",
    "compute.googleapis.com",
    "iam.googleapis.com",
    "iap.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
  ])
}

resource "google_project_service" "this" {
  for_each = local.services

  service = each.value
  # Never disable APIs on destroy: other resources (and the DNS zones) live in this project.
  disable_on_destroy         = false
  disable_dependent_services = false
}

# The IAP service agent (service-<number>@gcp-sa-iap.iam.gserviceaccount.com) only exists once
# it has been provisioned; the env roots grant it roles/run.invoker on the web services.
resource "google_project_service_identity" "iap" {
  provider = google-beta

  service    = "iap.googleapis.com"
  depends_on = [google_project_service.this]
}

# Remote state for shared/ and envs/*. The state contains generated DB passwords:
# keep this bucket private (uniform access + public access prevention, owners only).
resource "google_storage_bucket" "tfstate" {
  name     = var.state_bucket
  location = var.region

  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  # Keep state history bounded: drop non-current versions after 30 days (keep at least 5).
  lifecycle_rule {
    condition {
      with_state                 = "ARCHIVED"
      num_newer_versions         = 5
      days_since_noncurrent_time = 30
    }
    action {
      type = "Delete"
    }
  }

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_project_service.this]
}
