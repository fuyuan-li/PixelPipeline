# Figma CI Pipeline — Architecture & TODO

## Current State

The pipeline works end-to-end:

```
Figma Plugin → GitLab MR → intake → design_system_agent → design_auditor → review_writer
```

The Figma plugin lets the user select a design system from a predefined dropdown (MD3,
Apple HIG, Ant Design, etc.), exports the page nodes as JSON (including `boundVariables`
and `mainComponentName`), creates a branch + MR, and @-mentions the flow bot to trigger
the pipeline.

**Known limitation:** `design_system_agent` currently passes through an empty `variables: []`
list for named design systems (since they are component-only Figma libraries with no published
variable collections). The `design_auditor` therefore relies on the LLM's training knowledge
to match colors to tokens — which risks hallucination. The GCS + Cloud Function work below
is the fix.

---

## Next Major Feature: Real Token Data via Google Cloud

### Why

The `design_auditor` needs a ground-truth list of tokens (name → hex value) to:
1. Confirm whether a detached color matches a known token
2. Suggest the correct token name (not hallucinate one)
3. Produce a fix spec with the correct target hex value

### Design Systems in Scope (3 total)

| # | System | Why | Token source |
|---|--------|-----|--------------|
| 1 | **Material Design 3** (Google) | Most recognised; clear token JSON | `material-foundation/material-tokens` on GitHub |
| 2 | **Ant Design** (Alibaba) | Enterprise / Asia market; structured tokens | `ant-design/ant-design` on GitHub (`components/style/themes/`) |
| 3 | **Carbon Design System** (IBM) | Enterprise; cleanest open-source token JSON | `carbon-design-system/carbon` on GitHub (`packages/themes/src/tokens/`) |

Apple HIG and Fluent are excluded for now — no machine-readable public token files.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  tools/scraper/  (runs once locally, or via cron)        │
│  Python script — fetches raw JSON from GitHub,           │
│  normalises to common schema, uploads to GCS             │
└────────────────────┬────────────────────────────────────┘
                     │ gs://figma-design-tokens/
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Google Cloud Storage bucket                             │
│  figma-design-tokens/                                    │
│    md3.json                                              │
│    antd.json                                             │
│    carbon.json                                           │
└────────────────────┬────────────────────────────────────┘
                     │ HTTP GET
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Cloud Function: design-tokens-api                       │
│  GET ?system=md3[&type=COLOR][&q=primary]                │
│  → reads JSON from GCS, filters, returns token list      │
└────────────────────┬────────────────────────────────────┘
                     │ called by agent over HTTP
                     ▼
┌─────────────────────────────────────────────────────────┐
│  GitLab: design_system_agent                             │
│  Reads designSystem.name from Figma export               │
│  → calls Cloud Function → gets real token list           │
│  → commits design-system-standards.json with real data   │
└─────────────────────────────────────────────────────────┘
```

---

## File Structure (to be created)

```
tools/
  scraper/
    main.py            # entry point: runs all scrapers, uploads to GCS
    scrapers/
      md3.py           # fetches material-foundation/material-tokens
      antd.py          # fetches ant-design token definitions
      carbon.py        # fetches carbon-design-system theme tokens
    upload.py          # normalise + upload helpers
    requirements.txt   # google-cloud-storage, requests

gcloud/
  functions/
    design-tokens-api/
      main.py          # Cloud Function handler
      requirements.txt # google-cloud-storage
```

---

## Normalised Token Schema

Every JSON file stored in GCS follows this schema:

```json
{
  "system":    "Material Design 3",
  "version":   "scraped 2025-01-01",
  "tokens": [
    {
      "name":  "md.sys.color.primary",
      "value": "#6750A4",
      "type":  "COLOR",
      "group": "color"
    },
    {
      "name":  "md.sys.typescale.body-large.size",
      "value": "16",
      "type":  "FLOAT",
      "group": "typography"
    }
  ]
}
```

---

## Cloud Function API

**Endpoint:** `GET https://REGION-PROJECT.cloudfunctions.net/design-tokens-api`

**Query params:**

| Param | Required | Description |
|-------|----------|-------------|
| `system` | yes | `md3` \| `antd` \| `carbon` |
| `type` | no | `COLOR` \| `FLOAT` \| `STRING` — filter by token type |
| `q` | no | substring search on token name |

**Example:**
```
GET ?system=md3&type=COLOR
→ returns all MD3 colour tokens with name + hex value
```

**Response:**
```json
{
  "system": "Material Design 3",
  "count": 87,
  "tokens": [
    { "name": "md.sys.color.primary",    "value": "#6750A4", "type": "COLOR" },
    { "name": "md.sys.color.on-primary", "value": "#FFFFFF", "type": "COLOR" }
  ]
}
```

---

## Changes Needed to Existing Files

### `flows/figma-review.yml` — `design_system_agent` prompt

Add a step between current Step 4 and Step 5:

```
Step 4b: Map designSystem.name to a system slug:
  "Material Design 3"      → md3
  "Ant Design"             → antd
  "Carbon Design System"   → carbon
  (anything else)          → skip fetch, use empty variables

Step 4c: Call the Cloud Function:
  GET <CLOUD_FUNCTION_URL>?system=<slug>&type=COLOR
  Parse the JSON response. Use the "tokens" array as the variable list.
  Each token: { name, value (hex), type }
```

Then in Step 5, commit the Cloud Function's token list instead of the empty
`variables: []` from the Figma export.

### `agent-config.yml`

Add the Cloud Function URL to the network whitelist:
```yaml
network:
  allowed:
    - "*.cloudfunctions.net"
```

---

## GCP Setup Steps (to do together)

1. **Create GCP project** — in GCP Console, note the project ID
2. **Enable APIs** — Cloud Functions, Cloud Storage, Cloud Build
3. **Create GCS bucket** — `gs://figma-design-tokens` (or similar), region: us-central1
4. **Run scraper locally**
   ```bash
   cd tools/scraper
   pip install -r requirements.txt
   python main.py
   # → uploads md3.json, antd.json, carbon.json to GCS
   ```
5. **Deploy Cloud Function**
   ```bash
   cd gcloud/functions/design-tokens-api
   gcloud functions deploy design-tokens-api \
     --runtime python311 \
     --trigger-http \
     --allow-unauthenticated \
     --region us-central1 \
     --set-env-vars GCS_BUCKET=figma-design-tokens
   ```
6. **Note the deployed URL** — add to `agent-config.yml` + `design_system_agent` prompt
7. **Test end-to-end** — trigger the pipeline, confirm `design-system-standards.json`
   now has real token data

---

## What Is NOT Being Done (deliberate scope cuts)

- **Custom design systems** — excluded; no reliable token source for arbitrary systems
- **Apple HIG / Fluent** — excluded; no machine-readable public token files
- **Semantic / vector search** — not needed; simple name-substring matching is sufficient
  for the hackathon demo (Vertex AI Vector Search would be next step)
- **Automated scraper scheduling** — tokens don't change daily; one-time manual run is fine
- **Auth on Cloud Function** — public endpoint is fine for a hackathon demo
