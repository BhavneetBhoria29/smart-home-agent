variable "project_id" {
  type        = string
  description = "GCP project ID"
}

variable "region" {
  type    = string
  default = "europe-west3" # Frankfurt
}

variable "app_name" {
  type    = string
  default = "smart-home-agent"
}

variable "cluster_name" {
  type    = string
  default = "agents-autopilot"
}

variable "k8s_namespace" {
  type    = string
  default = "smart-home"
}

variable "k8s_service_account" {
  type    = string
  default = "smart-home-agent"
}
