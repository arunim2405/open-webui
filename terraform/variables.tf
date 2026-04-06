variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for all resources"
  type        = string
  default     = "europe-west1"
}

variable "zone" {
  description = "GCP zone (used by Cloud SQL)"
  type        = string
  default     = "europe-west1-b"
}

variable "domain" {
  description = "Custom domain for the application (e.g. openwebui.example.com)"
  type        = string
}

variable "db_password" {
  description = "PostgreSQL database password"
  type        = string
  sensitive   = true
}

variable "webui_secret_key" {
  description = "Open WebUI secret key for session signing"
  type        = string
  sensitive   = true
}

variable "zeroentropy_api_key" {
  description = "ZeroEntropy API key for medical RAG"
  type        = string
  sensitive   = true
}

variable "zeroentropy_collection" {
  description = "ZeroEntropy collection name"
  type        = string
  default     = "markdown_output"
}

variable "open_webui_image" {
  description = "Docker image for Open WebUI (full Artifact Registry path)"
  type        = string
  default     = ""
}

variable "cloud_run_cpu" {
  description = "Cloud Run CPU allocation"
  type        = string
  default     = "2"
}

variable "cloud_run_memory" {
  description = "Cloud Run memory allocation"
  type        = string
  default     = "2Gi"
}

variable "cloud_run_min_instances" {
  description = "Minimum Cloud Run instances"
  type        = number
  default     = 1
}

variable "cloud_run_max_instances" {
  description = "Maximum Cloud Run instances"
  type        = number
  default     = 4
}

locals {
  labels = {
    project-id = "rome"
  }

  db_name = "openwebui"
  db_user = "openwebui"

  image = var.open_webui_image != "" ? var.open_webui_image : "${var.region}-docker.pkg.dev/${var.project_id}/rome-registry/open-webui:latest"
}
