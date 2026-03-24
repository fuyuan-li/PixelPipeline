"""
Cloud Function: design-tokens-api
==================================
HTTP GET endpoint that returns design system tokens and component specs stored in GCS.

Endpoints:
    GET https://REGION-PROJECT.cloudfunctions.net/design-tokens-api
        ?system=md3            (required)  md3 | carbon | atlassian
        &resource=all          (optional)  all (default) | tokens | components
        &type=COLOR            (optional)  COLOR | FLOAT | STRING | BOOLEAN  (tokens only)
        &q=primary             (optional)  substring search on token name  (tokens only)
        &group=color           (optional)  filter by group field  (tokens only)

Responses:
  resource=tokens:
    {
      "system": "Material Design 3",
      "slug":   "md3",
      "count":  87,
      "tokens": [
        { "name": "md.sys.color.primary", "value": "#6750A4", "type": "COLOR", "group": "color" }
      ]
    }

  resource=components:
    {
      "system": "Material Design 3",
      "slug":   "md3",
      "count":  6,
      "components": [
        {
          "name": "Button",
          "figma_search_name": "Button",
          "variants": [...],
          "detection": { "name_keywords": [...], "height_range": [...], ... }
        }
      ]
    }

  resource=all (default):
    Combined tokens + components response.

Environment variables (set via gcloud deploy --set-env-vars):
    GCS_BUCKET   Name of the GCS bucket (default: figma-design-tokens)
"""

import json
import os
import functions_framework
from google.cloud import storage

GCS_BUCKET   = os.environ.get("GCS_BUCKET", "figma-design-tokens")
VALID_SLUGS  = {"md3", "carbon", "atlassian"}

# In-memory cache so repeated calls within the same instance don't re-hit GCS.
_cache: dict = {}


def _load_from_gcs(slug: str) -> dict | None:
    if slug in _cache:
        return _cache[slug]
    try:
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET)
        blob   = bucket.blob(f"{slug}.json")
        data   = json.loads(blob.download_as_text(encoding="utf-8"))
        _cache[slug] = data
        return data
    except Exception as e:
        print(f"GCS read error for {slug}: {e}")
        return None


@functions_framework.http
def design_tokens_api(request):
    # ── CORS headers (allow GitLab agent infra to call us) ──────────────────
    headers = {
        "Access-Control-Allow-Origin":  "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Content-Type":                 "application/json",
    }
    if request.method == "OPTIONS":
        return ("", 204, headers)

    # ── Parse query params ──────────────────────────────────────────────────
    slug     = (request.args.get("system")   or "").strip().lower()
    resource = (request.args.get("resource") or "all").strip().lower()
    ftype    = (request.args.get("type")     or "").strip().upper()
    query    = (request.args.get("q")        or "").strip().lower()
    group    = (request.args.get("group")    or "").strip().lower()

    if not slug:
        return (json.dumps({"error": "Missing required param: system"}), 400, headers)
    if slug not in VALID_SLUGS:
        return (json.dumps({"error": f"Unknown system '{slug}'. Valid: {sorted(VALID_SLUGS)}"}), 400, headers)
    if resource not in ("tokens", "components", "all"):
        return (json.dumps({"error": f"Unknown resource '{resource}'. Valid: tokens | components | all"}), 400, headers)

    # ── Load data ────────────────────────────────────────────────────────────
    data = _load_from_gcs(slug)
    if not data:
        return (json.dumps({"error": f"Token data for '{slug}' not found in GCS bucket '{GCS_BUCKET}'."}), 404, headers)

    system_name = data.get("system", slug)
    version     = data.get("version", "")
    response    = {"system": system_name, "slug": slug, "version": version}

    # ── Tokens ───────────────────────────────────────────────────────────────
    if resource in ("tokens", "all"):
        tokens = data.get("tokens", [])
        if ftype:
            tokens = [t for t in tokens if t.get("type", "").upper() == ftype]
        if query:
            tokens = [t for t in tokens if query in t.get("name", "").lower()]
        if group:
            tokens = [t for t in tokens if group in t.get("group", "").lower()]
        response["token_count"] = len(tokens)
        response["tokens"]      = tokens

    # ── Components ───────────────────────────────────────────────────────────
    if resource in ("components", "all"):
        components = data.get("components", [])
        response["component_count"] = len(components)
        response["components"]      = components

    return (json.dumps(response, ensure_ascii=False), 200, headers)
