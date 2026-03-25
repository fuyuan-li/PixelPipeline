#!/bin/bash
set -e

# Usage: ./push.sh "your commit message"
COMMIT_MSG="${1:-chore: update}"
PLUGIN_DIR="local/figma-ci-plugin"
PLUGIN_ZIP="$PLUGIN_DIR/figma-ci-plugin.zip"

# ── 0. Rebuild plugin zip ────────────────────────────────────────────────────
echo "🧩 Rebuilding Figma plugin zip"
rm -f "$PLUGIN_ZIP"
zip -j -q "$PLUGIN_ZIP" \
  "$PLUGIN_DIR/manifest.json" \
  "$PLUGIN_DIR/code.js" \
  "$PLUGIN_DIR/ui.html" \
  "$PLUGIN_DIR/README.md"

# ── 1. Stage all changes ──────────────────────────────────────────────────────
echo "📦 git add ."
git add .

# ── 2. Commit ─────────────────────────────────────────────────────────────────
echo "💬 git commit: $COMMIT_MSG"
git commit -m "$COMMIT_MSG"

# ── 3. Pull with rebase ───────────────────────────────────────────────────────
echo "⬇️  git pull --rebase"
git pull --rebase

# ── 4. Push ───────────────────────────────────────────────────────────────────
echo "⬆️  git push"
git push

# ── 5. Compute next tag ───────────────────────────────────────────────────────
# Fetch all tags from remote first so we don't miss any
git fetch --tags

LATEST_TAG=$(git tag --sort=-v:refname | head -n 1)

if [ -z "$LATEST_TAG" ]; then
  NEXT_TAG="v0.0.1"
  echo "🏷️  No existing tags found, starting at $NEXT_TAG"
else
  echo "🏷️  Latest tag: $LATEST_TAG"

  # Strip leading 'v' if present, then split into parts
  VERSION="${LATEST_TAG#v}"
  MAJOR=$(echo "$VERSION" | cut -d. -f1)
  MINOR=$(echo "$VERSION" | cut -d. -f2)
  PATCH=$(echo "$VERSION" | cut -d. -f3)

  # Increment patch; fall back to simple +1 suffix if format is unexpected
  if echo "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
    PATCH=$((PATCH + 1))
    NEXT_TAG="v${MAJOR}.${MINOR}.${PATCH}"
  else
    NEXT_TAG="${LATEST_TAG}-1"
    echo "⚠️  Tag format not semver, appending -1: $NEXT_TAG"
  fi
fi

# ── 6. Create and push new tag ────────────────────────────────────────────────
echo "🔖 Creating tag: $NEXT_TAG"
git tag "$NEXT_TAG"

echo "🚀 Pushing tag: $NEXT_TAG"
git push origin "$NEXT_TAG"

echo ""
echo "✅ Done! Committed, pushed, and tagged as $NEXT_TAG"
