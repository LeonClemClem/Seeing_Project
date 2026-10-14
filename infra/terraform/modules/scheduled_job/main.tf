# Cloud Scheduler job that starts a Cloud Run job execution through the Cloud Run Admin API v2
# (POST .../jobs/<name>:run) with an OAuth token minted for the scheduler service account.

data "google_project" "this" {}

# roles/run.invoker on a job grants run.jobs.run (its other permissions only apply to services),
# which is all :run needs. This is the role Google documents for scheduled job executions.
resource "google_cloud_run_v2_job_iam_member" "scheduler" {
  name     = var.job_name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.scheduler_service_account_email}"
}

resource "google_cloud_scheduler_job" "this" {
  name        = var.name
  region      = var.region
  description = "Runs Cloud Run job ${var.job_name}"
  schedule    = var.schedule
  time_zone   = var.time_zone

  attempt_deadline = "180s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${data.google_project.this.project_id}/locations/${var.region}/jobs/${var.job_name}:run"

    oauth_token {
      service_account_email = var.scheduler_service_account_email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }

  depends_on = [google_cloud_run_v2_job_iam_member.scheduler]
}
