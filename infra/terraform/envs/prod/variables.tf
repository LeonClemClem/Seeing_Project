variable "project_id" {
  type    = string
  default = "project-astrarome"
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "env" {
  type = string
}

variable "iap_members" {
  description = "Principals allowed through IAP to the web service (ignored when web_public)."
  type        = list(string)
}

variable "web_public" {
  description = "true: public web service (no IAP). false: IAP, iap_members only."
  type        = bool
  default     = false
}

variable "custom_domains" {
  description = "Domains mapped to the web service, verified in Search Console beforehand."
  type        = list(string)
  default     = []
}

variable "web_image" {
  description = "Initial web image (placeholder); deploy.sh rolls out real images."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "job_image" {
  description = "Initial batch/migrate image (placeholder); deploy.sh rolls out real images."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/job"
}

variable "web_max_instances" {
  type    = number
  default = 2
}

variable "batch_cpu" {
  type    = string
  default = "2"
}

variable "batch_memory" {
  type    = string
  default = "4Gi"
}

variable "batch_timeout_seconds" {
  type    = number
  default = 3600
}

variable "batch_max_retries" {
  type    = number
  default = 1
}

variable "batch_env" {
  type = map(string)
  default = {
    GRIB_DIR       = "/tmp/arome"
    FORECAST_HOURS = "51"
    RETENTION_DAYS = "14"
    LOG_LEVEL      = "INFO"
  }
}

variable "batch_schedule" {
  description = "Cron, UTC."
  type        = string
}

variable "deletion_protection" {
  type    = bool
  default = true
}
