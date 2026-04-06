# ---------- Global External Application Load Balancer ----------

# Serverless NEG pointing to Cloud Run
resource "google_compute_region_network_endpoint_group" "cloudrun_neg" {
  name                  = "rome-cloudrun-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"

  cloud_run {
    service = google_cloud_run_v2_service.openwebui.name
  }
}

# Backend service
resource "google_compute_backend_service" "default" {
  name                  = "rome-backend"
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"

  backend {
    group = google_compute_region_network_endpoint_group.cloudrun_neg.id
  }

  log_config {
    enable = true
  }
}

# URL map
resource "google_compute_url_map" "default" {
  name            = "rome-url-map"
  default_service = google_compute_backend_service.default.id
}

# ---------- SSL Certificate ----------

resource "google_compute_managed_ssl_certificate" "default" {
  name = "rome-ssl-cert"

  managed {
    domains = [var.domain]
  }
}

# HTTPS proxy
resource "google_compute_target_https_proxy" "default" {
  name             = "rome-https-proxy"
  url_map          = google_compute_url_map.default.id
  ssl_certificates = [google_compute_managed_ssl_certificate.default.id]
}

# Global static IP
resource "google_compute_global_address" "lb_ip" {
  name   = "rome-lb-ip"
  labels = local.labels
}

# Forwarding rule (HTTPS)
resource "google_compute_global_forwarding_rule" "https" {
  name                  = "rome-https-rule"
  target                = google_compute_target_https_proxy.default.id
  port_range            = "443"
  ip_address            = google_compute_global_address.lb_ip.address
  load_balancing_scheme = "EXTERNAL_MANAGED"
  labels                = local.labels
}

# ---------- HTTP → HTTPS redirect ----------

resource "google_compute_url_map" "http_redirect" {
  name = "rome-http-redirect"

  default_url_redirect {
    https_redirect         = true
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
    strip_query            = false
  }
}

resource "google_compute_target_http_proxy" "http_redirect" {
  name    = "rome-http-redirect-proxy"
  url_map = google_compute_url_map.http_redirect.id
}

resource "google_compute_global_forwarding_rule" "http_redirect" {
  name                  = "rome-http-redirect-rule"
  target                = google_compute_target_http_proxy.http_redirect.id
  port_range            = "80"
  ip_address            = google_compute_global_address.lb_ip.address
  load_balancing_scheme = "EXTERNAL_MANAGED"
  labels                = local.labels
}
