variable "name" {
  description = "Cloud Scheduler job name."
  type        = string
}

variable "region" {
  type = string
}

variable "job_name" {
  description = "Cloud Run job to execute (same project/region)."
  type        = string
}

variable "schedule" {
  description = "Cron expression."
  type        = string
}

variable "time_zone" {
  type    = string
  default = "Etc/UTC"
}

variable "scheduler_service_account_email" {
  type = string
}
