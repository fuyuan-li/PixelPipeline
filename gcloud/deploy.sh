#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Full deployment of the Design Tokens API
#
# What this does (in order):
#   1. terraform init + apply  → creates GCS bucket + deploys Cloud Function
#   2. Runs the Python scraper → populates GCS with md3.json / carbon.json / atlassian.json
#   3. Smoke-tests the Cloud Function
#   4. Patches flows/figma-review.yml with the real Cloud Function URL
#
# Prerequisites:
#   - gcloud CLI installed and authenticated (gcloud auth application-default login)
#   - terraform CLI installed (https://developer.hashicorp.com/terraform/install)
#   - python3 available
#
# Usage:
#   cd gcloud
#   bash deploy.sh
# =============================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TERRAFORM_DIR="$REPO_ROOT/gcloud/terraform"
SCRAPER_DIR="$REPO_ROOT/tools/scraper"
FLOW_FILE="$REPO_ROOT/flows/figma-review.yml"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${GREEN}[deploy]${NC} $*"; }
warning() { echo -e "${YELLOW}[warn]${NC}   $*"; }
error()   { echo -e "${RED}[error]${NC}  $*"; exit 1; }

# ── 0. Sanity checks ──────────────────────────────────────────────────────────

command -v terraform >/dev/null 2>&1 || error "terraform not found. Install from https://developer.hashicorp.com/terraform/install"
command -v gcloud    >/dev/null 2>&1 || error "gcloud not found. Install from https://cloud.google.com/sdk/docs/install"
command -v python3   >/dev/null 2>&1 || error "python3 not found."

info "Checking gcloud authentication..."
gcloud auth application-default print-access-token >/dev/null 2>&1 \
  || error "Not authenticated. Run: gcloud auth application-default login"

# ── Ensure current user has Storage Admin on the project ──────────────────────
CURRENT_USER=$(gcloud config get-value account 2>/dev/null)
PROJECT_ID=$(grep 'project_id' "$TERRAFORM_DIR/terraform.tfvars" | awk -F'"' '{print $2}')
info "Ensuring storage.admin role for $CURRENT_USER..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="user:${CURRENT_USER}" \
  --role="roles/storage.admin" \
  --quiet >/dev/null 2>&1 || warning "Could not grant storage.admin (may already exist or lack permission)"

# ── 1. Terraform ──────────────────────────────────────────────────────────────

info "Running terraform init..."
mkdir -p "$TERRAFORM_DIR/.build"
cd "$TERRAFORM_DIR"
terraform init -upgrade -input=false

# ── Import existing GCS bucket if it already exists (avoids 409 conflict) ─────
BUCKET_NAME_VAR=$(grep 'bucket_name' "$TERRAFORM_DIR/terraform.tfvars" | awk -F'"' '{print $2}')
if ! terraform state show google_storage_bucket.tokens >/dev/null 2>&1; then
  if gcloud storage buckets describe "gs://${BUCKET_NAME_VAR}" >/dev/null 2>&1; then
    info "Bucket gs://${BUCKET_NAME_VAR} already exists — importing into Terraform state..."
    terraform import google_storage_bucket.tokens "$BUCKET_NAME_VAR"
  fi
fi

info "Running terraform apply..."
terraform apply -input=false -auto-approve

FUNCTION_URL=$(terraform output -raw function_url)
BUCKET_NAME=$(terraform output -raw bucket_name)

info "Cloud Function deployed: $FUNCTION_URL"
info "GCS bucket:              gs://$BUCKET_NAME"

# ── 2. Scraper — populate GCS with token data ─────────────────────────────────

info "Setting up Python venv for scraper..."
cd "$SCRAPER_DIR"

# Recreate venv if it doesn't exist or is broken (e.g. created on a different machine)
if [ ! -d ".venv" ] || ! .venv/bin/pip --version >/dev/null 2>&1; then
  info "Creating fresh Python venv..."
  rm -rf .venv
  python3 -m venv .venv
fi

.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

info "Running scraper (md3, carbon, atlassian)..."
.venv/bin/python main.py --bucket "$BUCKET_NAME"

# ── 3. Smoke test ─────────────────────────────────────────────────────────────

info "Smoke-testing Cloud Function..."
sleep 3  # brief pause for cold start

HTTP_STATUS=$(curl -s -o /tmp/cf_response.json -w "%{http_code}" \
  "${FUNCTION_URL}?system=md3&type=COLOR")

if [ "$HTTP_STATUS" = "200" ]; then
  TOKEN_COUNT=$(python3 -c "import json,sys; d=json.load(open('/tmp/cf_response.json')); print(d['count'])" 2>/dev/null || echo "?")
  info "✓ Cloud Function OK — MD3 returns $TOKEN_COUNT colour tokens"
else
  warning "Cloud Function returned HTTP $HTTP_STATUS — check GCP logs if unexpected"
  cat /tmp/cf_response.json 2>/dev/null || true
fi

# ── 4. Patch figma-review.yml ─────────────────────────────────────────────────

info "Patching flows/figma-review.yml with Cloud Function URL..."
cd "$REPO_ROOT"

# Replace the placeholder URL (whether it's the original placeholder or an old run.app URL)
# Always overwrite with the latest deployed URL
sed -i.bak \
  -e "s|https://REGION-PROJECT.cloudfunctions.net/design-tokens-api|${FUNCTION_URL}|g" \
  -e "s|https://design-tokens-api-[a-z0-9]*-uc\.a\.run\.app|${FUNCTION_URL}|g" \
  "$FLOW_FILE"
rm -f "${FLOW_FILE}.bak"
info "✓ figma-review.yml updated with: $FUNCTION_URL"

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN} Deployment complete!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo "  Cloud Function URL : $FUNCTION_URL"
echo "  GCS bucket         : gs://$BUCKET_NAME"
echo ""
echo "  Quick test:"
echo "    curl '${FUNCTION_URL}?system=md3&type=COLOR'"
echo "    curl '${FUNCTION_URL}?system=atlassian'"
echo "    curl '${FUNCTION_URL}?system=carbon&group=text'"
echo ""
echo "  Next: commit & push to GitLab, then test the full pipeline."
echo ""
