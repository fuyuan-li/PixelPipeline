terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ── Enable required GCP APIs ───────────────────────────────────────────────────

resource "google_project_service" "cloudfunctions" {
  service            = "cloudfunctions.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloudbuild" {
  service            = "cloudbuild.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "run" {
  # Gen 2 Cloud Functions run on top of Cloud Run
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "storage" {
  service            = "storage.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "artifactregistry" {
  service            = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}

# ── GCS bucket for token data ──────────────────────────────────────────────────

resource "google_storage_bucket" "tokens" {
  name          = var.bucket_name
  location      = var.region
  force_destroy = false # don't wipe token data on terraform destroy

  uniform_bucket_level_access = true

  lifecycle_rule {
    condition { age = 365 }
    action    { type = "Delete" }
  }
}

# ── Zip and upload Cloud Function source ───────────────────────────────────────

data "archive_file" "function_source" {
  type        = "zip"
  source_dir  = "${path.module}/../functions/design-tokens-api"
  output_path = "${path.module}/.build/design-tokens-api.zip"
}

resource "google_storage_bucket_object" "function_zip" {
  name   = "function-source/design-tokens-api-${data.archive_file.function_source.output_md5}.zip"
  bucket = google_storage_bucket.tokens.name
  source = data.archive_file.function_source.output_path

  depends_on = [google_storage_bucket.tokens]
}

# ── Cloud Function (2nd gen) ───────────────────────────────────────────────────

resource "google_cloudfunctions2_function" "api" {
  name     = var.function_name
  location = var.region

  build_config {
    runtime     = "python311"
    entry_point = "design_tokens_api"
    source {
      storage_source {
        bucket = google_storage_bucket.tokens.name
        object = google_storage_bucket_object.function_zip.name
      }
    }
  }

  service_config {
    available_memory      = "256M"
    timeout_seconds       = 30
    max_instance_count    = 10
    environment_variables = {
      GCS_BUCKET = google_storage_bucket.tokens.name
    }
  }

  depends_on = [
    google_project_service.cloudfunctions,
    google_project_service.cloudbuild,
    google_project_service.run,
  ]
}

# ── Make the function publicly invocable (no auth required) ───────────────────
# Gen 2 functions sit behind Cloud Run, so the IAM is on the Cloud Run service

resource "google_cloud_run_service_iam_member" "public_invoker" {
  project  = var.project_id
  location = var.region
  service  = google_cloudfunctions2_function.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ── Grant Cloud Function's service account read access to the token bucket ────
# Gen 2 functions run as the default compute service account

data "google_project" "project" {}

resource "google_storage_bucket_iam_member" "cf_gcs_reader" {
  bucket = google_storage_bucket.tokens.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}
