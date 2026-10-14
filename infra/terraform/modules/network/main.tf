# Custom-mode VPC with one regional subnet (Private Google Access on, so the DB VM without an
# external IP can reach Artifact Registry, Secret Manager and Cloud Logging) and the two
# firewall rules the stack needs. No Cloud NAT: nothing in the VPC needs public egress.

resource "google_compute_network" "this" {
  name                    = var.network_name
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
}

resource "google_compute_subnetwork" "this" {
  name                     = var.subnet_name
  network                  = google_compute_network.this.id
  region                   = var.region
  ip_cidr_range            = var.subnet_cidr
  private_ip_google_access = true
}

# Postgres: only from inside the subnet (DB VM itself and Cloud Run Direct VPC egress addresses).
resource "google_compute_firewall" "allow_postgres" {
  name      = "${var.network_name}-allow-postgres"
  network   = google_compute_network.this.id
  direction = "INGRESS"
  priority  = 1000

  source_ranges = [var.subnet_cidr]
  target_tags   = [var.db_target_tag]

  allow {
    protocol = "tcp"
    ports    = ["5432"]
  }
}

# SSH (and optionally Postgres) through Identity-Aware Proxy TCP forwarding only.
resource "google_compute_firewall" "allow_iap" {
  name      = "${var.network_name}-allow-iap"
  network   = google_compute_network.this.id
  direction = "INGRESS"
  priority  = 1000

  source_ranges = ["35.235.240.0/20"]

  allow {
    protocol = "tcp"
    ports    = var.iap_tcp_ports
  }
}
