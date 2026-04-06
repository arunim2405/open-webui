# ---------- Secret Manager ----------

resource "google_secret_manager_secret" "db_password" {
  secret_id = "rome-db-password"
  labels    = local.labels

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = var.db_password
}

resource "google_secret_manager_secret" "webui_secret_key" {
  secret_id = "rome-webui-secret-key"
  labels    = local.labels

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "webui_secret_key" {
  secret      = google_secret_manager_secret.webui_secret_key.id
  secret_data = var.webui_secret_key
}

resource "google_secret_manager_secret" "zeroentropy_api_key" {
  secret_id = "rome-zeroentropy-api-key"
  labels    = local.labels

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "zeroentropy_api_key" {
  secret      = google_secret_manager_secret.zeroentropy_api_key.id
  secret_data = var.zeroentropy_api_key
}
