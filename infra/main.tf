terraform {
  required_version = ">= 1.8"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
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
    "artifactregistry.googleapis.com",
    "firestore.googleapis.com",
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

resource "google_firestore_database" "aegis" {
  project                     = var.project_id
  name                        = "(default)"
  location_id                 = var.firestore_location
  type                        = "FIRESTORE_NATIVE"
  deletion_policy             = "ABANDON"
  app_engine_integration_mode = "DISABLED"
  depends_on                  = [google_project_service.services]
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
    "roles/datastore.user",
    "roles/pubsub.subscriber",
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
    service_account = google_service_account.runtime.email
    containers {
      image = var.image
      env {
        name  = "AEGIS_ENVIRONMENT"
        value = "production"
      }
      env {
        name  = "AEGIS_STORAGE_BACKEND"
        value = "firestore"
      }
      env {
        name  = "AEGIS_GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      resources {
        limits = { cpu = "1", memory = "512Mi" }
      }
    }
    scaling {
      min_instance_count = 0
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
  push_config {
    push_endpoint = "${google_cloud_run_v2_service.aegis.uri}/api/v1/pubsub"
    oidc_token {
      service_account_email = google_service_account.runtime.email
    }
  }
}
