variable "project_id" {
  type = string
}

variable "env" {
  description = "dev or prod."
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.env)
    error_message = "env must be dev or prod."
  }
}

variable "region" {
  type = string
}

variable "network_id" {
  type = string
}

variable "subnet_id" {
  type = string
}

variable "db_host" {
  type = string
}

variable "db_port" {
  type    = number
  default = 5432
}

variable "db_password_secret_id" {
  description = "Secret Manager secret id holding this environment's DB password."
  type        = string
}

variable "scheduler_service_account_email" {
  type = string
}

variable "deployer_service_account_email" {
  description = "SA of the GitHub Actions deployer; may act as this env's runtime SAs."
  type        = string
}

variable "iap_members" {
  type = list(string)
}

variable "web_public" {
  description = "Serve the web service publicly instead of behind IAP."
  type        = bool
  default     = false
}

variable "custom_domains" {
  description = "Custom domains mapped to the web service."
  type        = list(string)
  default     = []
}

variable "web_image" {
  type = string
}

variable "job_image" {
  description = "Initial image for the batch and migrate jobs (placeholder until the first deploy)."
  type        = string
}

variable "web_max_instances" {
  type    = number
  default = 2
}

variable "batch_cpu" {
  type = string
}

variable "batch_memory" {
  type = string
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
  description = "Batch-only env vars (GRIB_DIR, FORECAST_HOURS, RETENTION_DAYS, LOG_LEVEL)."
  type        = map(string)
  default     = {}
}

variable "batch_schedule" {
  description = "Cron (UTC) for the batch job."
  type        = string
}

variable "deletion_protection" {
  type    = bool
  default = true
}

variable "email_verification" {
  description = "Require the e-mail confirmation of new accounts (Brevo). The brevo-api-key-<env> secret must have a version first."
  type        = bool
  default     = false
}

variable "mail_from" {
  description = "Sender of the e-mails, on a domain authenticated in Brevo (SPF / DKIM)."
  type        = string
  default     = "no-reply@seeingthesky.com"
}

variable "public_url" {
  description = "Base URL of the site, for the links in the e-mails."
  type        = string
  default     = "https://seeingthesky.com"
}
