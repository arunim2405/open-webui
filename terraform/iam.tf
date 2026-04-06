# ---------- Service Account for Cloud Run ----------

resource "google_service_account" "cloud_run" {
  account_id   = "rome-cloud-run"
  display_name = "Rome Cloud Run Service Account"
}

# Cloud SQL Client
resource "google_project_iam_member" "cloud_run_sql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

# GCS Object Admin (upload/download/delete files)
resource "google_storage_bucket_iam_member" "cloud_run_gcs" {
  bucket = google_storage_bucket.uploads.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.cloud_run.email}"
}

# Secret Manager Accessor
resource "google_secret_manager_secret_iam_member" "db_password" {
  secret_id = google_secret_manager_secret.db_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_secret_manager_secret_iam_member" "webui_secret_key" {
  secret_id = google_secret_manager_secret.webui_secret_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_secret_manager_secret_iam_member" "zeroentropy_api_key" {
  secret_id = google_secret_manager_secret.zeroentropy_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud_run.email}"
}
