variable "project_id" {
  description = "Google Cloud project ID"
  type        = string
}

variable "region" {
  description = "Cloud Run, Artifact Registry, Vertex AI and Model Armor region"
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

variable "mode" {
  description = "Runtime mode: mock (no spend), cached, or live"
  type        = string
  default     = "live"

  validation {
    condition     = contains(["mock", "cached", "live"], var.mode)
    error_message = "mode must be one of mock, cached, live."
  }
}

variable "adjudicator_model" {
  description = "Gemini model backing the re-adjudication agent"
  type        = string
  default     = "gemini-2.5-flash"
}

variable "enable_model_armor" {
  description = "Create the hosted Model Armor template and point the shields at it"
  type        = bool
  default     = true
}

variable "min_instances" {
  description = "Warm instances. Zero costs nothing and adds cold start to the demo."
  type        = number
  default     = 0
}
