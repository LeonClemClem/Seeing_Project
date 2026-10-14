terraform {
  required_version = ">= 1.10.0"

  backend "gcs" {
    bucket = "project-astrarome-tfstate"
    prefix = "shared"
  }

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone

  # The Billing Budgets API refuses end-user credentials without a quota project.
  user_project_override = true
  billing_project       = var.project_id
}
