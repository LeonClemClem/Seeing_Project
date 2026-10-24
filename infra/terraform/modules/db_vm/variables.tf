variable "project_id" {
  type = string
}

variable "name" {
  type    = string
  default = "seeing-db"
}

variable "region" {
  type = string
}

variable "zone" {
  type = string
}

variable "machine_type" {
  description = "e2-micro is in the always-free tier (us-central1/us-east1/us-west1)."
  type        = string
  default     = "e2-micro"
}

variable "subnet_id" {
  type = string
}

variable "internal_ip" {
  type    = string
  default = "10.10.0.10"
}

variable "network_tag" {
  type    = string
  default = "seeing-db"
}

variable "service_account_id" {
  type    = string
  default = "seeing-db-vm"
}

variable "boot_disk_size_gb" {
  type    = number
  default = 10
}

variable "data_disk_name" {
  type    = string
  default = "seeing-db-data"
}

variable "data_disk_size_gb" {
  description = "Boot + data must stay <= 30 GB pd-standard to remain in the free tier."
  type        = number
  default     = 10
}

variable "snapshot_start_time" {
  description = "Daily snapshot start (UTC, HH:00)."
  type        = string
  default     = "03:00"
}

variable "snapshot_retention_days" {
  type    = number
  default = 7
}

variable "postgres_image" {
  description = "Postgres image, pulled through the Artifact Registry Docker Hub remote repository."
  type        = string
}

variable "image_repository_id" {
  description = "Artifact Registry repository (in var.region) the VM may pull from."
  type        = string
}

variable "superuser_secret_id" {
  description = "Secret Manager secret holding the postgres superuser password."
  type        = string
}

variable "databases" {
  description = "Database name (also its owner role name) => Secret Manager secret id holding that role's password."
  type        = map(string)
}

variable "client_cidrs" {
  description = "CIDRs allowed to reach Postgres (pg_hba + host firewall)."
  type        = list(string)
}

variable "db_client_cidrs" {
  description = "Database name => extra CIDRs allowed in pg_hba for that database only (also opened in the host firewall)."
  type        = map(list(string))
  default     = {}
}

variable "pg_max_connections" {
  type    = number
  default = 40
}

variable "pg_shared_buffers" {
  type    = string
  default = "128MB"
}

variable "pg_effective_cache_size" {
  type    = string
  default = "384MB"
}

variable "pg_work_mem" {
  type    = string
  default = "4MB"
}
