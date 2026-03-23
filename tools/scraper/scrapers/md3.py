"""
Scraper for Material Design 3 tokens.

Primary source:
  material-foundation/material-tokens — JSON files following W3C design tokens spec.
  Directory listing via GitHub Contents API, then individual file fetch.

Fallback:
  Curated baseline M3 light-scheme color tokens (stable values from the spec).
  These are the official values published at m3.material.io/styles/color/static-color-schemes.
"""

import re
import json
import requests

GITHUB_API   = "https://api.github.com/repos/material-foundation/material-tokens/contents"
GITHUB_RAW   = "https://raw.githubusercontent.com/material-foundation/material-tokens/main"
HEADERS      = {"Accept": "application/vnd.github.v3+json", "User-Agent": "figma-ci-scraper/1.0"}
TIMEOUT      = 15

# ── Fallback: M3 Baseline Light Scheme ────────────────────────────────────────
# Source: https://m3.material.io/styles/color/static-color-schemes
FALLBACK_COLORS = {
    # Primary
    "md.sys.color.primary":              "#6750A4",
    "md.sys.color.on-primary":           "#FFFFFF",
    "md.sys.color.primary-container":    "#EADDFF",
    "md.sys.color.on-primary-container": "#21005D",
    # Secondary
    "md.sys.color.secondary":              "#625B71",
    "md.sys.color.on-secondary":           "#FFFFFF",
    "md.sys.color.secondary-container":    "#E8DEF8",
    "md.sys.color.on-secondary-container": "#1D192B",
    # Tertiary
    "md.sys.color.tertiary":              "#7D5260",
    "md.sys.color.on-tertiary":           "#FFFFFF",
    "md.sys.color.tertiary-container":    "#FFD8E4",
    "md.sys.color.on-tertiary-container": "#31111D",
    # Error
    "md.sys.color.error":              "#B3261E",
    "md.sys.color.on-error":           "#FFFFFF",
    "md.sys.color.error-container":    "#F9DEDC",
    "md.sys.color.on-error-container": "#410E0B",
    # Surface / Background
    "md.sys.color.background":          "#FFFBFE",
    "md.sys.color.on-background":       "#1C1B1F",
    "md.sys.color.surface":             "#FFFBFE",
    "md.sys.color.on-surface":          "#1C1B1F",
    "md.sys.color.surface-variant":     "#E7E0EC",
    "md.sys.color.on-surface-variant":  "#49454F",
    "md.sys.color.surface-container-lowest":  "#FFFFFF",
    "md.sys.color.surface-container-low":     "#F7F2FA",
    "md.sys.color.surface-container":         "#F3EDF7",
    "md.sys.color.surface-container-high":    "#ECE6F0",
    "md.sys.color.surface-container-highest": "#E6E0E9",
    # Outline
    "md.sys.color.outline":         "#79747E",
    "md.sys.color.outline-variant": "#CAC4D0",
    # Misc
    "md.sys.color.shadow":           "#000000",
    "md.sys.color.scrim":            "#000000",
    "md.sys.color.inverse-surface":   "#313033",
    "md.sys.color.inverse-on-surface":"#F4EFF4",
    "md.sys.color.inverse-primary":   "#D0BCFF",
}

# ── Typography tokens (stable spec values) ────────────────────────────────────
FALLBACK_TYPOGRAPHY = {
    "md.sys.typescale.display-large.size":   "57",
    "md.sys.typescale.display-medium.size":  "45",
    "md.sys.typescale.display-small.size":   "36",
    "md.sys.typescale.headline-large.size":  "32",
    "md.sys.typescale.headline-medium.size": "28",
    "md.sys.typescale.headline-small.size":  "24",
    "md.sys.typescale.title-large.size":     "22",
    "md.sys.typescale.title-medium.size":    "16",
    "md.sys.typescale.title-small.size":     "14",
    "md.sys.typescale.label-large.size":     "14",
    "md.sys.typescale.label-medium.size":    "12",
    "md.sys.typescale.label-small.size":     "11",
    "md.sys.typescale.body-large.size":      "16",
    "md.sys.typescale.body-medium.size":     "14",
    "md.sys.typescale.body-small.size":      "12",
}


def _parse_w3c_tokens(obj, prefix=""):
    """Recursively parse W3C design tokens format { name: { $value, $type } }."""
    tokens = []
    for key, val in obj.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(val, dict):
            if "$value" in val:
                t = val.get("$type", "").upper()
                raw = val["$value"]
                value = raw if isinstance(raw, str) else str(raw)
                tokens.append({
                    "name":  full_key,
                    "value": value,
                    "type":  "COLOR" if t in ("COLOR", "COLOUR") or value.startswith("#") else "FLOAT" if t == "NUMBER" else "STRING",
                    "group": full_key.split(".")[2] if full_key.count(".") >= 2 else "misc",
                })
            else:
                tokens.extend(_parse_w3c_tokens(val, full_key))
    return tokens


def _try_github_fetch():
    """Attempt to list and fetch token JSON files from the GitHub repo."""
    tokens = []
    try:
        resp = requests.get(f"{GITHUB_API}/tokens", headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        files = resp.json()
        json_files = [f for f in files if f["name"].endswith(".json") and "color" in f["name"].lower()]
        if not json_files:
            json_files = [f for f in files if f["name"].endswith(".json")][:5]

        for f in json_files:
            try:
                raw = requests.get(f["download_url"], headers=HEADERS, timeout=TIMEOUT)
                raw.raise_for_status()
                data = raw.json()
                tokens.extend(_parse_w3c_tokens(data))
            except Exception:
                continue
    except Exception:
        pass
    return tokens


def scrape():
    """Return normalised M3 token list."""
    tokens = _try_github_fetch()

    if not tokens:
        # Build from curated fallback
        for name, value in FALLBACK_COLORS.items():
            group = name.split(".")[2] if name.count(".") >= 2 else "color"
            tokens.append({"name": name, "value": value, "type": "COLOR", "group": group})
        for name, value in FALLBACK_TYPOGRAPHY.items():
            tokens.append({"name": name, "value": value, "type": "FLOAT", "group": "typography"})

    return {
        "system":  "Material Design 3",
        "slug":    "md3",
        "version": "baseline-light",
        "source":  "material-foundation/material-tokens (GitHub) or curated fallback",
        "tokens":  tokens,
    }
