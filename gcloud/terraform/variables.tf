variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for Cloud Function and GCS bucket"
  type        = string
  default     = "us-central1"
}

variable "bucket_name" {
  description = "GCS bucket name for storing design system token JSON files"
  type        = string
}

variable "function_name" {
  description = "Name of the Cloud Function"
  type        = string
  default     = "design-tokens-api"
}
