output "image_repo" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.repo.repository_id}"
}

output "cluster_name" {
  value = google_container_cluster.autopilot.name
}

output "gcp_service_account" {
  value = google_service_account.agent.email
}
