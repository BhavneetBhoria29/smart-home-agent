terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

data "google_project" "this" {}

locals {
  services = [
    "container.googleapis.com",
    "artifactregistry.googleapis.com",
    "aiplatform.googleapis.com",
    "iam.googleapis.com",
  ]
}

resource "google_project_service" "apis" {
  for_each           = toset(local.services)
  service            = each.value
  disable_on_destroy = false
}

# ---------- Container registry ----------
resource "google_artifact_registry_repository" "repo" {
  location      = var.region
  repository_id = var.app_name
  format        = "DOCKER"
  depends_on    = [google_project_service.apis]
}

# Autopilot nodes run as the default compute SA; let them pull the image.
resource "google_artifact_registry_repository_iam_member" "node_pull" {
  location   = google_artifact_registry_repository.repo.location
  repository = google_artifact_registry_repository.repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${data.google_project.this.number}-compute@developer.gserviceaccount.com"
}

# ---------- GKE Autopilot ----------
resource "google_container_cluster" "autopilot" {
  name                = var.cluster_name
  location            = var.region
  enable_autopilot    = true
  deletion_protection = false
  depends_on          = [google_project_service.apis]
}

# ---------- Runtime identity (no API keys in the cluster) ----------
resource "google_service_account" "agent" {
  account_id   = var.app_name
  display_name = "Smart Home Agent runtime"
}

resource "google_project_iam_member" "vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.agent.email}"
}

# Workload Identity: the K8s service account impersonates the GCP one.
resource "google_service_account_iam_member" "workload_identity" {
  service_account_id = google_service_account.agent.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${var.k8s_namespace}/${var.k8s_service_account}]"
  depends_on         = [google_container_cluster.autopilot]
}
