# Postgres on an always-free e2-micro: Container-Optimized OS, no external IP, postgres container
# started by a systemd unit written by cloud-init, data on a separate persistent disk that is
# snapshotted daily.

data "google_compute_image" "cos" {
  family  = "cos-stable"
  project = "cos-cloud"
}

locals {
  registry_host = "${var.region}-docker.pkg.dev"

  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    project              = var.project_id
    image                = var.postgres_image
    registry_host        = local.registry_host
    data_device_name     = var.data_disk_name
    mount_dir            = "/mnt/disks/pgdata"
    superuser_secret     = var.superuser_secret_id
    databases            = var.databases
    client_cidrs         = var.client_cidrs
    max_connections      = var.pg_max_connections
    shared_buffers       = var.pg_shared_buffers
    effective_cache_size = var.pg_effective_cache_size
    work_mem             = var.pg_work_mem
  })
}

# --- Service account (least privilege) ---------------------------------------------------------

resource "google_service_account" "vm" {
  account_id   = var.service_account_id
  display_name = "Seeing DB VM"
}

resource "google_project_iam_member" "vm" {
  for_each = toset(["roles/logging.logWriter", "roles/monitoring.metricWriter"])

  project = var.project_id
  role    = each.value
  member  = google_service_account.vm.member
}

resource "google_artifact_registry_repository_iam_member" "vm_pull" {
  location   = var.region
  repository = var.image_repository_id
  role       = "roles/artifactregistry.reader"
  member     = google_service_account.vm.member
}

resource "google_secret_manager_secret_iam_member" "vm" {
  for_each = toset(concat([var.superuser_secret_id], values(var.databases)))

  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.vm.member
}

# --- Disks & backups ----------------------------------------------------------------------------

resource "google_compute_address" "internal" {
  name         = "${var.name}-internal"
  region       = var.region
  subnetwork   = var.subnet_id
  address_type = "INTERNAL"
  address      = var.internal_ip
}

resource "google_compute_disk" "data" {
  name = var.data_disk_name
  zone = var.zone
  type = "pd-standard"
  size = var.data_disk_size_gb

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_compute_resource_policy" "snapshots" {
  name   = "${var.data_disk_name}-daily"
  region = var.region

  snapshot_schedule_policy {
    schedule {
      daily_schedule {
        days_in_cycle = 1
        start_time    = var.snapshot_start_time
      }
    }
    retention_policy {
      max_retention_days    = var.snapshot_retention_days
      on_source_disk_delete = "KEEP_AUTO_SNAPSHOTS"
    }
    snapshot_properties {
      storage_locations = [var.region]
      labels            = { app = "seeing", disk = var.data_disk_name }
    }
  }
}

resource "google_compute_disk_resource_policy_attachment" "snapshots" {
  name = google_compute_resource_policy.snapshots.name
  disk = google_compute_disk.data.name
  zone = var.zone
}

# --- VM -----------------------------------------------------------------------------------------

resource "google_compute_instance" "db" {
  name         = var.name
  zone         = var.zone
  machine_type = var.machine_type
  tags         = [var.network_tag]

  allow_stopping_for_update = true

  boot_disk {
    auto_delete = true
    initialize_params {
      image = data.google_compute_image.cos.self_link
      size  = var.boot_disk_size_gb
      type  = "pd-standard"
    }
  }

  attached_disk {
    source      = google_compute_disk.data.id
    device_name = var.data_disk_name
    mode        = "READ_WRITE"
  }

  network_interface {
    subnetwork = var.subnet_id
    network_ip = google_compute_address.internal.address
    # No access_config block => no external IP. Google APIs via Private Google Access.
  }

  metadata = {
    user-data                 = local.user_data
    enable-oslogin            = "TRUE"
    block-project-ssh-keys    = "TRUE"
    google-logging-enabled    = "true"
    google-monitoring-enabled = "true"
  }

  service_account {
    email  = google_service_account.vm.email
    scopes = ["cloud-platform"]
  }

  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
    preemptible         = false
  }

  labels = { app = "seeing", role = "db" }

  lifecycle {
    # cos-stable moves every few weeks; COS updates itself in place, don't recreate the VM.
    ignore_changes = [boot_disk[0].initialize_params[0].image]
  }

  depends_on = [
    google_secret_manager_secret_iam_member.vm,
    google_artifact_registry_repository_iam_member.vm_pull,
  ]
}
