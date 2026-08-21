# ---------- Cloud Run Service ----------

resource "google_cloud_run_v2_service" "openwebui" {
  name     = "rome-openwebui"
  location = var.region
  labels   = local.labels

  ingress = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    labels          = local.labels
    service_account = google_service_account.cloud_run.email

    scaling {
      min_instance_count = var.cloud_run_min_instances
      max_instance_count = var.cloud_run_max_instances
    }

    # Direct VPC egress (replaced the rome-connector: its use was denied by an
    # org-side policy layer as of 2026-08; private-IP DB stays reachable, public
    # egress goes direct from Cloud Run instead of via NAT).
    vpc_access {
      egress = "PRIVATE_RANGES_ONLY"
      network_interfaces {
        network    = google_compute_network.vpc.id
        subnetwork = google_compute_subnetwork.private.id
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.postgres.connection_name]
      }
    }

    containers {
      image = local.image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = var.cloud_run_cpu
          memory = var.cloud_run_memory
        }
      }

      # ---------- Environment Variables ----------

      env {
        name  = "DATABASE_URL"
        value = "postgresql://${local.db_user}:${var.db_password}@${google_sql_database_instance.postgres.private_ip_address}:5432/${local.db_name}"
      }

      env {
        name  = "STORAGE_PROVIDER"
        value = "gcs"
      }

      env {
        name  = "GCS_BUCKET_NAME"
        value = google_storage_bucket.uploads.name
      }

      env {
        name = "WEBUI_SECRET_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.webui_secret_key.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "ZEROENTROPY_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.zeroentropy_api_key.secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "ZEROENTROPY_COLLECTION"
        value = var.zeroentropy_collection
      }

      # rome search API — the functions read these as their valve defaults.
      # Flipping RETRIEVAL_BACKEND to "rome" is the cutover (docs/runbooks/cutover.md
      # in the rome-ingestion-search repo); the service account already holds
      # roles/run.invoker on rome-search-api.
      env {
        name  = "SEARCH_API_URL"
        value = var.search_api_url
      }

      env {
        name  = "RETRIEVAL_BACKEND"
        value = var.retrieval_backend
      }

      # Disable local embedding model download — using ZeroEntropy for RAG
      env {
        name  = "RAG_EMBEDDING_ENGINE"
        value = ""
      }

      env {
        name  = "RAG_EMBEDDING_MODEL_AUTO_UPDATE"
        value = "false"
      }

      # Medical assistant settings (from docker-compose.medical.yaml)
      env {
        name  = "ENABLE_OLLAMA_API"
        value = "false"
      }

      env {
        name  = "WEBUI_NAME"
        value = "Rome Medical Assistant"
      }

      env {
        name  = "DEFAULT_MODELS"
        value = "gpt-5.4"
      }

      env {
        name  = "ENABLE_IMAGE_GENERATION"
        value = "false"
      }

      env {
        name  = "ENABLE_COMMUNITY_SHARING"
        value = "false"
      }

      env {
        name  = "ENABLE_WEB_SEARCH"
        value = "false"
      }

      env {
        name  = "ENABLE_CODE_INTERPRETER"
        value = "false"
      }

      env {
        name  = "WEBUI_AUTH"
        value = "true"
      }

      env {
        name  = "WEBUI_BANNERS"
        value = "[{\"id\":\"medical-disclaimer\",\"type\":\"warning\",\"content\":\"⚕️ Research Tool Only — Responses are generated from indexed medical literature and do not constitute medical advice. Always consult qualified healthcare professionals for clinical decisions.\",\"dismissible\":false,\"timestamp\":0}]"
      }

      # Cloud SQL via unix socket (fallback — private IP is primary)
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      startup_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        initial_delay_seconds = 30
        period_seconds        = 10
        failure_threshold     = 30
      }

      liveness_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        period_seconds    = 30
        failure_threshold = 3
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_version.webui_secret_key,
    google_secret_manager_secret_version.zeroentropy_api_key,
    google_secret_manager_secret_version.db_password,
  ]
}

# Allow unauthenticated access (app handles its own auth)
resource "google_cloud_run_v2_service_iam_member" "public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.openwebui.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
