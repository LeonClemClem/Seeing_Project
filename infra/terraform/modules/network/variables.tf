variable "region" {
  type = string
}

variable "network_name" {
  type    = string
  default = "seeing-vpc"
}

variable "subnet_name" {
  type    = string
  default = "seeing-us-central1"
}

variable "subnet_cidr" {
  type    = string
  default = "10.10.0.0/24"
}

variable "db_target_tag" {
  description = "Network tag carried by the DB VM; the Postgres rule targets it."
  type        = string
  default     = "seeing-db"
}

variable "iap_tcp_ports" {
  description = "Ports reachable from the IAP TCP forwarding range (35.235.240.0/20)."
  type        = list(string)
  default     = ["22"]
}
