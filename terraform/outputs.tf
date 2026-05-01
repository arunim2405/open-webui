output "cloud_run_url" {
  description = "Direct Cloud Run service URL"
  value       = google_cloud_run_v2_service.openwebui.uri
}

output "load_balancer_ip" {
  description = "Global load balancer IP — point your domain's A record here"
  value       = google_compute_global_address.lb_ip.address
}

output "artifact_registry" {
  description = "Docker push target"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/rome-registry/open-webui"
}

output "gcs_bucket" {
  description = "GCS bucket for file uploads"
  value       = google_storage_bucket.uploads.name
}
output "db_connection_name" {
  description = "Cloud SQL connection name (for local proxy)"
  value       = google_sql_database_instance.postgres.connection_name
}

output "db_private_ip" {
  description = "Cloud SQL private IP"
  value       = google_sql_database_instance.postgres.private_ip_address
}

output "pdf_signer_email" {
  description = "PDF signer service account email"
  value       = google_service_account.pdf_signer.email
}

output "pdf_signer_key_json" {
  description = "PDF signer service account key JSON — paste into plugin Valves > GCS_CREDENTIALS_JSON"
  value       = base64decode(google_service_account_key.pdf_signer_key.private_key)
  sensitive   = true
}
