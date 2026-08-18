output "service_url" {
  value = google_cloud_run_v2_service.aegis.uri
}

output "repository" {
  value = google_artifact_registry_repository.aegis.name
}

output "decision_topic" {
  value = google_pubsub_topic.decisions.id
}

