# ---------- Cloud SQL (PostgreSQL) ----------

resource "google_sql_database_instance" "postgres" {
  name             = "rome-postgres"
  database_version = "POSTGRES_18"
  region           = var.region
  # edition          = "ENTERPRISE"

  settings {
    tier              = "db-custom-2-8192"
    availability_type = "ZONAL"
    disk_size         = 10
    disk_type         = "PD_SSD"
    disk_autoresize   = true

    user_labels = local.labels

    ip_configuration {
      ipv4_enabled                                  = false
      private_network                               = google_compute_network.vpc.id
      enable_private_path_for_google_cloud_services = true
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "03:00"
      transaction_log_retention_days = 7
    }

    database_flags {
      name  = "max_connections"
      value = "100"
    }
  }

  deletion_protection = true

  depends_on = [google_service_networking_connection.private_vpc_connection]
}

resource "google_sql_database" "openwebui" {
  name     = local.db_name
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "openwebui" {
  name     = local.db_user
  instance = google_sql_database_instance.postgres.name
  password = var.db_password
}
