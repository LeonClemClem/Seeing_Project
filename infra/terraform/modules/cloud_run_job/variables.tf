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

variable "command" {
  description = "Entrypoint override (null = image default)."
  type        = list(string)
  default     = null
}

variable "args" {
  type    = list(string)
  default = null
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

variable "cpu" {
  type    = string
  default = "1"
}

variable "memory" {
  type    = string
  default = "512Mi"
}

variable "timeout_seconds" {
  type    = number
  default = 600
}

variable "max_retries" {
  type    = number
  default = 0
}

variable "env" {
  type    = map(string)
  default = {}
}

variable "secret_env" {
  description = "Environment variable name => Secret Manager secret id (version latest)."
  type        = map(string)
  default     = {}
}

variable "deletion_protection" {
  type    = bool
  default = true
}
