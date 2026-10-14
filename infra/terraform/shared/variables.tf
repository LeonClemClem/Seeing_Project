variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "zone" {
  type = string
}

variable "billing_account" {
  description = "Billing account id (budget alerts)."
  type        = string
}

variable "environments" {
  description = "Environments sharing the DB VM; one database/role/secret each."
  type        = list(string)
  default     = ["dev", "prod"]
}

variable "subnet_cidr" {
  type    = string
  default = "10.10.0.0/24"
}

variable "db_internal_ip" {
  type    = string
  default = "10.10.0.10"
}

variable "iap_tcp_ports" {
  description = "Ports open to IAP TCP forwarding (35.235.240.0/20). SSH only by default."
  type        = list(string)
  default     = ["22"]
}

variable "registry_keep_versions" {
  description = "Most recent versions kept per image in the `seeing` repository."
  type        = number
  default     = 5
}

variable "budget_amount_usd" {
  description = "Monthly budget; alerts at 100% and 200% of it."
  type        = number
  default     = 10
}

variable "alert_emails" {
  description = "E-mail addresses that receive budget alerts (max 5)."
  type        = list(string)
}
