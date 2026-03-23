output "function_url" {
  description = "Cloud Function HTTP endpoint — paste this into flows/figma-review.yml"
  value       = google_cloudfunctions2_function.api.service_config[0].uri
}

output "bucket_name" {
  description = "GCS bucket storing token JSON files"
  value       = google_storage_bucket.tokens.name
}

output "verify_command" {
  description = "Quick smoke-test command — run after deploy"
  value       = "curl '${google_cloudfunctions2_function.api.service_config[0].uri}?system=md3&type=COLOR' | python3 -m json.tool | head -30"
}
