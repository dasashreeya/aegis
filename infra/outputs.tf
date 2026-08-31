output "service_url" {
  description = "Public URL of the Aegis Cloud Run service"
  value       = google_cloud_run_v2_service.aegis.uri
}

output "repository" {
  description = "Artifact Registry repository the image is pushed to"
  value       = google_artifact_registry_repository.aegis.name
}

output "decision_topic" {
  description = "Pub/Sub topic decisions are published to"
  value       = google_pubsub_topic.decisions.id
}

output "dead_letter_topic" {
  description = "Where decisions that fail five audit attempts are parked"
  value       = google_pubsub_topic.decisions_dead_letter.id
}

output "runtime_service_account" {
  description = "Identity the fleet runs as"
  value       = google_service_account.runtime.email
}

output "model_armor_template" {
  description = "Template id to set as AEGIS_MODEL_ARMOR_TEMPLATE"
  value       = var.enable_model_armor ? google_model_armor_template.aegis[0].template_id : ""
}

output "push_endpoint" {
  description = "Where Pub/Sub delivers decisions"
  value       = "${google_cloud_run_v2_service.aegis.uri}/api/v1/pubsub"
}
