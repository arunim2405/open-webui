# ---------- GCS Bucket (file uploads) ----------

resource "google_storage_bucket" "uploads" {
  name     = "${var.project_id}-rome-uploads"
  location = var.region
  labels   = local.labels

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      num_newer_versions = 3
    }
  }
}

# ---------- Artifact Registry ----------

resource "google_artifact_registry_repository" "registry" {
  location      = var.region
  repository_id = "rome-registry"
  format        = "DOCKER"
  labels        = local.labels

  depends_on = [google_project_service.apis]
}
