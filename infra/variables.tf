variable "project_id" {
  description = "Google Cloud project ID"
  type        = string
}

variable "region" {
  description = "Cloud Run and Artifact Registry region"
  type        = string
  default     = "us-central1"
}

variable "firestore_location" {
  description = "Firestore database location"
  type        = string
  default     = "nam5"
}

variable "image" {
  description = "Aegis container image URI"
  type        = string
}

