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

# ---------- Service Account for PDF signed URL generation ----------

resource "google_service_account" "pdf_signer" {
  account_id   = "rome-pdf-signer"
  display_name = "Rome PDF Signer Service Account"
}

# Read-only access to the uploads bucket (PDFs only)
resource "google_storage_bucket_iam_member" "pdf_signer_uploads" {
  bucket = google_storage_bucket.uploads.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.pdf_signer.email}"
}

# JSON key for signing URLs (paste into plugin Valves > GCS_CREDENTIALS_JSON)
resource "google_service_account_key" "pdf_signer_key" {
  service_account_id = google_service_account.pdf_signer.name
  public_key_type    = "TYPE_X509_PEM_FILE"
}
