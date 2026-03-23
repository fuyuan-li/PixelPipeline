"""
Scraper for IBM Carbon Design System tokens.

Primary source:
  carbon-design-system/carbon — packages/themes/src/tokens/*.js
  These are plain JS files that export objects of token→value.

Fallback:
  Curated Carbon White theme tokens (the default / most-used theme).
"""

import re
import json
import requests

GITHUB_RAW = "https://raw.githubusercontent.com/carbon-design-system/carbon/main"
TIMEOUT    = 15

# ── Theme files to fetch ──────────────────────────────────────────────────────
THEME_FILES = {
    "white": f"{GITHUB_RAW}/packages/themes/src/tokens/white.js",
    "g10":   f"{GITHUB_RAW}/packages/themes/src/tokens/g10.js",
}

# ── Fallback: Carbon White theme ──────────────────────────────────────────────
# Source: https://carbondesignsystem.com/elements/color/tokens/
FALLBACK_COLORS = {
    # Background
    "background":            "#ffffff",
    "background-active":     "#c6c6c6",
    "background-hover":      "#e8e8e8",
    "background-selected":   "#e0e0e0",
    "background-inverse":    "#393939",
    # Layer
    "layer-01":              "#f4f4f4",
    "layer-02":              "#ffffff",
    "layer-03":              "#f4f4f4",
    "layer-active-01":       "#c6c6c6",
    "layer-hover-01":        "#e8e8e8",
    "layer-selected-01":     "#e0e0e0",
    # Border
    "border-subtle-00":      "#e0e0e0",
    "border-subtle-01":      "#c6c6c6",
    "border-strong-01":      "#8d8d8d",
    "border-inverse":        "#161616",
    "border-interactive":    "#0f62fe",
    # Text
    "text-primary":          "#161616",
    "text-secondary":        "#525252",
    "text-placeholder":      "#a8a8a8",
    "text-disabled":         "#c6c6c6",
    "text-inverse":          "#ffffff",
    "text-on-color":         "#ffffff",
    "text-error":            "#da1e28",
    # Link
    "link-primary":          "#0f62fe",
    "link-primary-hover":    "#0043ce",
    "link-secondary":        "#0043ce",
    "link-inverse":          "#78a9ff",
    # Icon
    "icon-primary":          "#161616",
    "icon-secondary":        "#525252",
    "icon-inverse":          "#ffffff",
    "icon-on-color":         "#ffffff",
    "icon-disabled":         "#c6c6c6",
    # Interactive
    "interactive":           "#0f62fe",
    "focus":                 "#0f62fe",
    "focus-inverse":         "#ffffff",
    "highlight":             "#d0e2ff",
    # Support
    "support-error":         "#da1e28",
    "support-success":       "#198038",
    "support-warning":       "#f1c21b",
    "support-info":          "#0043ce",
    "support-error-inverse": "#fa4d56",
    # Miscellaneous
    "overlay":               "#16161680",
    "skeleton-element":      "#e0e0e0",
    "skeleton-background":   "#e5e5e5",
}

FALLBACK_SPACING = {
    "spacing-01": "2",
    "spacing-02": "4",
    "spacing-03": "8",
    "spacing-04": "12",
    "spacing-05": "16",
    "spacing-06": "24",
    "spacing-07": "32",
    "spacing-08": "40",
    "spacing-09": "48",
    "spacing-10": "64",
    "spacing-11": "80",
    "spacing-12": "96",
    "spacing-13": "160",
}

FALLBACK_TYPOGRAPHY = {
    "body-compact-01-font-size":   "14",
    "body-compact-02-font-size":   "16",
    "body-01-font-size":           "14",
    "body-02-font-size":           "16",
    "label-01-font-size":          "12",
    "label-02-font-size":          "14",
    "helper-text-01-font-size":    "12",
    "code-01-font-size":           "12",
    "code-02-font-size":           "14",
    "heading-compact-01-font-size":"14",
    "heading-compact-02-font-size":"16",
    "heading-01-font-size":        "14",
    "heading-02-font-size":        "16",
    "heading-03-font-size":        "20",
    "heading-04-font-size":        "28",
    "heading-05-font-size":        "36",
    "heading-06-font-size":        "42",
    "heading-07-font-size":        "54",
    "fluid-heading-03-font-size":  "20",
    "fluid-heading-04-font-size":  "28",
    "fluid-heading-05-font-size":  "36",
    "fluid-heading-06-font-size":  "42",
}


def _parse_js_tokens(js_source):
    """
    Parse tokens from Carbon's JS theme files.
    These export plain objects like:
        export const white = {
          background: '#ffffff',
          ...
        };
    We extract key: '#value' pairs with a regex.
    """
    tokens = []
    # Match  tokenName: '#hexvalue'  or  tokenName: "rgba(...)"
    pattern = re.compile(r"(\w[\w-]*):\s*'([^']+)'")
    for match in pattern.finditer(js_source):
        name, value = match.group(1), match.group(2)
        if value.startswith("#") or value.startswith("rgb"):
            tokens.append({
                "name":  name,
                "value": value,
                "type":  "COLOR",
                "group": _infer_group(name),
            })
    return tokens


def _infer_group(name):
    for prefix in ("text", "icon", "link", "border", "layer", "background",
                   "support", "interactive", "focus", "field", "overlay"):
        if name.startswith(prefix):
            return prefix
    return "misc"


def _try_github_fetch():
    """Fetch and parse Carbon token JS files from GitHub."""
    tokens = []
    for theme, url in THEME_FILES.items():
        try:
            resp = requests.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            parsed = _parse_js_tokens(resp.text)
            if parsed:
                tokens = parsed  # use first successful theme
                break
        except Exception:
            continue
    return tokens


def scrape():
    """Return normalised Carbon token list."""
    tokens = _try_github_fetch()

    source = "carbon-design-system/carbon (GitHub)"
    if not tokens:
        source = "curated fallback (GitHub unavailable)"
        for name, value in FALLBACK_COLORS.items():
            tokens.append({"name": name, "value": value, "type": "COLOR", "group": _infer_group(name)})
        for name, value in FALLBACK_SPACING.items():
            tokens.append({"name": name, "value": value, "type": "FLOAT", "group": "spacing"})
        for name, value in FALLBACK_TYPOGRAPHY.items():
            tokens.append({"name": name, "value": value, "type": "FLOAT", "group": "typography"})

    return {
        "system":  "Carbon Design System",
        "slug":    "carbon",
        "version": "white-theme",
        "source":  source,
        "tokens":  tokens,
    }
