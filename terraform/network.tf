# ---------- VPC ----------

resource "google_compute_network" "vpc" {
  name                    = "rome-vpc"
  auto_create_subnetworks = false

  depends_on = [google_project_service.apis]
}

# ---------- Subnets ----------

resource "google_compute_subnetwork" "private" {
  name                     = "rome-private"
  ip_cidr_range            = "10.10.0.0/24"
  region                   = var.region
  network                  = google_compute_network.vpc.id
  private_ip_google_access = true
}

# Dedicated subnet for VPC connector (must be /28)
resource "google_compute_subnetwork" "connector" {
  name          = "rome-vpc-connector"
  ip_cidr_range = "10.10.1.0/28"
  region        = var.region
  network       = google_compute_network.vpc.id
}

# ---------- Cloud NAT (outbound internet for private resources) ----------

resource "google_compute_router" "router" {
  name    = "rome-router"
  region  = var.region
  network = google_compute_network.vpc.id
}

resource "google_compute_router_nat" "nat" {
  name                               = "rome-nat"
  router                             = google_compute_router.router.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}

# ---------- Private Service Access (Cloud SQL private IP) ----------

resource "google_compute_global_address" "private_ip_range" {
  name          = "rome-private-ip"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc.id
  labels        = local.labels
}

resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_range.name]

  depends_on = [google_project_service.apis]
}

# ---------- VPC Connector (Cloud Run → VPC) ----------

resource "google_vpc_access_connector" "connector" {
  name   = "rome-connector"
  region = var.region

  subnet {
    name = google_compute_subnetwork.connector.name
  }

  min_instances = 2
  max_instances = 3

  depends_on = [google_project_service.apis]
}

# ---------- Firewall ----------

resource "google_compute_firewall" "allow_internal" {
  name    = "rome-allow-internal"
  network = google_compute_network.vpc.id

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "icmp"
  }

  source_ranges = ["10.10.0.0/16"]
}

resource "google_compute_firewall" "allow_health_checks" {
  name    = "rome-allow-health-checks"
  network = google_compute_network.vpc.id

  allow {
    protocol = "tcp"
    ports    = ["8080"]
  }

  # Google health check IP ranges
  source_ranges = ["130.211.0.0/22", "35.191.0.0/16"]
}
