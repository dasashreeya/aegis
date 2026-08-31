terraform {
  required_version = ">= 1.8"
  required_providers {
    google = {
      source = "hashicorp/google"
      # google_model_armor_template landed in 6.14. Pin above it so a fresh
      # `terraform init` cannot resolve a provider that lacks the resource.
      version = ">= 6.14, < 7.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

data "google_project" "current" {
  project_id = var.project_id
}

resource "google_project_service" "services" {
  for_each = toset([
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudtrace.googleapis.com",
    "firestore.googleapis.com",
    "modelarmor.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "aegis" {
  location      = var.region
  repository_id = "aegis"
  format        = "DOCKER"
  depends_on    = [google_project_service.services]
}

resource "google_pubsub_topic" "decisions" {
  name       = "aegis-decisions"
  depends_on = [google_project_service.services]
}

resource "google_pubsub_topic" "decisions_dead_letter" {
  name       = "aegis-decisions-dead-letter"
  depends_on = [google_project_service.services]
}

resource "google_firestore_database" "aegis" {
  project                     = var.project_id
  name                        = "(default)"
  location_id                 = var.firestore_location
  type                        = "FIRESTORE_NATIVE"
  deletion_policy             = "ABANDON"
  app_engine_integration_mode = "DISABLED"
  depends_on                  = [google_project_service.services]
}

# The ledger is append-only in the application. This index is what makes
# reading one decision back in sequence order cheap.
resource "google_firestore_index" "ledger_by_decision" {
  project    = var.project_id
  database   = google_firestore_database.aegis.name
  collection = "decision_ledger"

  fields {
    field_path = "decision_id"
    order      = "ASCENDING"
  }
  fields {
    field_path = "sequence"
    order      = "ASCENDING"
  }
}

# Screens every inbound claim narrative and every generated rationale.
resource "google_model_armor_template" "aegis" {
  count       = var.enable_model_armor ? 1 : 0
  provider    = google
  location    = var.region
  template_id = "aegis-shield"

  # Required by the Model Armor API on update; all fields are optional but the
  # block itself is not. Logging is on so shield operations show in the console.
  template_metadata {
    log_sanitize_operations = true
    log_template_operations = true
  }

  filter_config {
    rai_settings {
      rai_filters {
        filter_type      = "DANGEROUS"
        confidence_level = "MEDIUM_AND_ABOVE"
      }
      rai_filters {
        filter_type      = "HARASSMENT"
        confidence_level = "MEDIUM_AND_ABOVE"
      }
    }
    pi_and_jailbreak_filter_settings {
      filter_enforcement = "ENABLED"
      confidence_level   = "LOW_AND_ABOVE"
    }
    malicious_uri_filter_settings {
      filter_enforcement = "ENABLED"
    }
    sdp_settings {
      basic_config {
        filter_enforcement = "ENABLED"
      }
    }
  }

  depends_on = [google_project_service.services]
}

resource "google_service_account" "runtime" {
  account_id   = "aegis-runtime"
  display_name = "Aegis Cloud Run runtime"
}

resource "google_service_account_iam_member" "pubsub_token_creator" {
  service_account_id = google_service_account.runtime.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
  depends_on         = [google_project_service.services]
}

resource "google_project_iam_member" "runtime_roles" {
  for_each = toset([
    "roles/aiplatform.user",     # Gemini re-adjudication on Vertex
    "roles/cloudtrace.agent",    # OpenTelemetry export
    "roles/datastore.user",      # decisions and the ledger
    "roles/logging.logWriter",   # structured logs
    "roles/modelarmor.user",     # the input and output shields
    "roles/pubsub.subscriber",   # the decision stream
    "roles/telemetry.tracesWriter",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_cloud_run_v2_service" "aegis" {
  name     = "aegis"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account       = google_service_account.runtime.email
    max_instance_request_concurrency = 40
    timeout               = "120s"

    containers {
      image = var.image

      env {
        name  = "AEGIS_ENVIRONMENT"
        value = "production"
      }
      # Real Vertex, real Model Armor, real Cloud Trace.
      env {
        name  = "AEGIS_MODE"
        value = var.mode
      }
      env {
        name  = "AEGIS_STORAGE_BACKEND"
        value = "firestore"
      }
      env {
        name  = "AEGIS_GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "AEGIS_GOOGLE_CLOUD_LOCATION"
        value = var.region
      }
      env {
        name  = "AEGIS_MODEL_ADJUDICATOR"
        value = var.adjudicator_model
      }
      env {
        name  = "AEGIS_FLEET_RUNTIME"
        value = "adk"
      }
      env {
        name  = "AEGIS_TRACE_EXPORTER"
        value = "cloud"
      }
      env {
        name  = "AEGIS_MODEL_ARMOR_TEMPLATE"
        value = var.enable_model_armor ? google_model_armor_template.aegis[0].template_id : ""
      }
      env {
        name  = "AEGIS_MODEL_ARMOR_LOCATION"
        value = var.region
      }

      resources {
        limits = { cpu = "2", memory = "2Gi" }
        # BatchSpanProcessor exports on a background thread. With CPU throttled
        # between requests that thread never runs and spans never reach Cloud
        # Trace. Instances still scale to zero, so this costs nothing at idle.
        cpu_idle = false
        # The ADK fleet and Z3 both benefit; the first request otherwise pays
        # for the whole import graph.
        startup_cpu_boost = true
      }

      startup_probe {
        # Building the fleet happens on the first request, which is this one.
        # A revision that cannot reach Vertex never takes traffic.
        initial_delay_seconds = 5
        timeout_seconds       = 10
        period_seconds        = 10
        failure_threshold     = 6
        http_get {
          path = "/api/health"
        }
      }

      liveness_probe {
        period_seconds    = 30
        timeout_seconds   = 5
        failure_threshold = 3
        http_get {
          path = "/api/health"
        }
      }
    }

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = 10
    }
  }

  depends_on = [google_project_service.services, google_firestore_database.aegis]
}

resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.aegis.name
  location = google_cloud_run_v2_service.aegis.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_pubsub_subscription" "decisions" {
  name  = "aegis-decisions-push"
  topic = google_pubsub_topic.decisions.id

  ack_deadline_seconds = 120

  push_config {
    push_endpoint = "${google_cloud_run_v2_service.aegis.uri}/api/v1/pubsub"
    oidc_token {
      service_account_email = google_service_account.runtime.email
    }
  }

  # A decision that cannot be audited after five attempts is parked rather than
  # redelivered forever.
  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.decisions_dead_letter.id
    max_delivery_attempts = 5
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }
}
