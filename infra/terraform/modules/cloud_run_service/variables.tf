variable "name" {
  type = string
}

variable "region" {
  type = string
}

variable "image" {
  description = "Initial image only; later rollouts are done by deploy.sh and ignored by Terraform."
  type        = string
}

variable "service_account_email" {
  type = string
}

variable "network" {
  type = string
}

variable "subnetwork" {
  type = string
}

variable "port" {
  type    = number
  default = 8080
}

variable "health_path" {
  type    = string
  default = "/healthz"
}

variable "cpu" {
  type    = string
  default = "1"
}

variable "memory" {
  type    = string
  default = "512Mi"
}

variable "min_instances" {
  type    = number
  default = 0
}

variable "max_instances" {
  type    = number
  default = 2
}

variable "concurrency" {
  type    = number
  default = 80
}

variable "env" {
  description = "Plain environment variables."
  type        = map(string)
  default     = {}
}

variable "secret_env" {
  description = "Environment variable name => Secret Manager secret id (version latest)."
  type        = map(string)
  default     = {}
}

variable "iap_members" {
  description = "Principals granted roles/iap.httpsResourceAccessor (e.g. user:someone@gmail.com)."
  type        = list(string)
}

variable "deletion_protection" {
  type    = bool
  default = true
}
