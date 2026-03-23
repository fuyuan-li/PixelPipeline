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

GITHUB_RAW = "https://raw.githubusercontent.com/material-foundation/material-tokens/main"
HEADERS    = {"User-Agent": "figma-ci-scraper/1.0"}
TIMEOUT    = 15

# DSP tokens.json: flat list of entities with type/id/value
DSP_TOKENS_URL = f"{GITHUB_RAW}/dsp/data/tokens.json"

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


def _hex8_to_hex6(value: str) -> str:
    """Convert #rrggbbaa → #rrggbb (strip alpha)."""
    v = value.strip()
    if v.startswith("#") and len(v) == 9:
        return v[:7]
    return v


def _try_github_fetch():
    """Fetch tokens from material-foundation/material-tokens DSP format."""
    tokens = []
    try:
        resp = requests.get(DSP_TOKENS_URL, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        entities = data.get("entities", [])
        for e in entities:
            if not isinstance(e, dict) or e.get("class") != "token":
                continue
            tok_type = e.get("type", "").lower()
            name     = e.get("id") or e.get("name", "")
            value    = str(e.get("value", "")).strip()
            if not name or not value:
                continue
            if tok_type == "color":
                tokens.append({
                    "name":  name,
                    "value": _hex8_to_hex6(value),
                    "type":  "COLOR",
                    "group": name.split(".")[2] if name.count(".") >= 2 else "color",
                })
            elif tok_type in ("number", "float", "dimension"):
                tokens.append({
                    "name":  name,
                    "value": value,
                    "type":  "FLOAT",
                    "group": name.split(".")[2] if name.count(".") >= 2 else "misc",
                })
    except Exception:
        pass
    return tokens


def scrape():
    """Return normalised M3 data: component catalog (primary) + tokens (supplementary)."""
    tokens = _try_github_fetch()

    source = "material-foundation/material-tokens (GitHub)"
    if not tokens:
        source = "curated fallback (GitHub unavailable)"
        for name, value in FALLBACK_COLORS.items():
            group = name.split(".")[2] if name.count(".") >= 2 else "color"
            tokens.append({"name": name, "value": value, "type": "COLOR", "group": group})
        for name, value in FALLBACK_TYPOGRAPHY.items():
            tokens.append({"name": name, "value": value, "type": "FLOAT", "group": "typography"})

    return {
        "system":     "Material Design 3",
        "slug":       "md3",
        "version":    "baseline-light",
        "source":     source,
        # Component catalog — primary data for the DS Migration pipeline.
        # Each entry describes a UI component, its variants, and the structural
        # signals the Component Classifier uses to recognise raw Figma shapes.
        "components": MD3_COMPONENTS,
        # Tokens retained for reference / future use.
        "tokens":     tokens,
    }


# ── MD3 Component Catalog ─────────────────────────────────────────────────────
# Curated from https://m3.material.io/components
# detection rules are used by the Component Classifier agent to infer the
# semantic type of raw FRAME / RECTANGLE nodes in the Figma export.

MD3_COMPONENTS = [
    {
        "name":             "Button",
        "category":         "action",
        "description":      "Buttons help people initiate actions.",
        "figma_search_name": "Button",
        "variants": [
            {"name": "Filled Button",   "figma_name": "Button/Filled Button"},
            {"name": "Outlined Button", "figma_name": "Button/Outlined Button"},
            {"name": "Text Button",     "figma_name": "Button/Text Button"},
            {"name": "Elevated Button", "figma_name": "Button/Elevated Button"},
            {"name": "Tonal Button",    "figma_name": "Button/Filled Tonal Button"},
        ],
        "detection": {
            "name_keywords":       ["button", "btn", "cta", "action", "submit", "confirm"],
            "node_types":          ["FRAME", "RECTANGLE"],
            "height_range":        [32, 56],
            "max_width":           240,
            "requires_text_child": True,
            "notes": "Frame 32–56px tall, ≤240px wide, with a TEXT child.",
        },
    },
    {
        "name":             "List Item",
        "category":         "containment",
        "description":      "Lists display a continuous, vertical index of text or images.",
        "figma_search_name": "List Item",
        "variants": [
            {"name": "1-line", "figma_name": "Lists/1-line item"},
            {"name": "2-line", "figma_name": "Lists/2-line item"},
            {"name": "3-line", "figma_name": "Lists/3-line item"},
        ],
        "detection": {
            "name_keywords":       ["song", "track", "item", "row", "list", "entry", "music"],
            "node_types":          ["FRAME"],
            "height_range":        [48, 88],
            "min_width":           200,
            "requires_text_child": True,
            "notes": "Full-width frame (≥200px), 48–88px tall, repeating as siblings.",
        },
    },
    {
        "name":             "Navigation Bar",
        "category":         "navigation",
        "description":      "Navigation bars offer a persistent way to switch between primary destinations.",
        "figma_search_name": "Navigation Bar",
        "variants": [
            {"name": "Navigation Bar", "figma_name": "Navigation Bar/Navigation Bar"},
        ],
        "detection": {
            "name_keywords": ["nav bar", "navigation", "tab bar", "bottom nav",
                              "section 4", "navbar"],
            "node_types":    ["FRAME"],
            "height_range":  [56, 96],
            "min_width":     300,
            "notes": "Full-width frame (≥300px), 56–96px tall. 3–5 icon+label destinations.",
        },
    },
    {
        "name":             "Divider",
        "category":         "containment",
        "description":      "Dividers are thin lines that group content in lists and layouts.",
        "figma_search_name": "Divider",
        "variants": [
            {"name": "Full-width Divider", "figma_name": "Divider/Divider"},
            {"name": "Inset Divider",      "figma_name": "Divider/Inset divider"},
        ],
        "detection": {
            "name_keywords": ["rectangle", "divider", "separator", "line", "hr"],
            "node_types":    ["RECTANGLE", "FRAME", "LINE"],
            "max_height":    4,
            "min_width":     100,
            "notes": "Thin element (height ≤ 4px, width > 100px). Raw RECTANGLE used as separator.",
        },
    },
    {
        "name":             "Card",
        "category":         "containment",
        "description":      "Cards contain content and actions about a single subject.",
        "figma_search_name": "Card",
        "variants": [
            {"name": "Filled Card",   "figma_name": "Cards/Filled card"},
            {"name": "Outlined Card", "figma_name": "Cards/Outlined card"},
            {"name": "Elevated Card", "figma_name": "Cards/Elevated card"},
        ],
        "detection": {
            "name_keywords":     ["card", "tile", "panel"],
            "node_types":        ["FRAME"],
            "min_corner_radius": 8,
            "notes": "Frame with cornerRadius ≥ 8, containing headline text.",
        },
    },
    {
        "name":             "Top App Bar",
        "category":         "navigation",
        "description":      "Top app bars display navigation and actions for the current screen.",
        "figma_search_name": "Top App Bar",
        "variants": [
            {"name": "Center-aligned", "figma_name": "Top app bar/Center-aligned"},
            {"name": "Small",          "figma_name": "Top app bar/Small"},
            {"name": "Medium",         "figma_name": "Top app bar/Medium"},
            {"name": "Large",          "figma_name": "Top app bar/Large"},
        ],
        "detection": {
            "name_keywords": ["top bar", "app bar", "header", "toolbar",
                              "section 1", "section 2", "section 3"],
            "node_types":    ["FRAME"],
            "height_range":  [56, 152],
            "min_width":     300,
            "notes": "Full-width frame at top of screen, 56–152px tall.",
        },
    },
    {
        "name":             "Chip",
        "category":         "action",
        "description":      "Chips help people enter information, make selections, or trigger actions.",
        "figma_search_name": "Chip",
        "variants": [
            {"name": "Assist Chip",     "figma_name": "Chips/Assist chip"},
            {"name": "Filter Chip",     "figma_name": "Chips/Filter chip"},
            {"name": "Input Chip",      "figma_name": "Chips/Input chip"},
            {"name": "Suggestion Chip", "figma_name": "Chips/Suggestion chip"},
        ],
        "detection": {
            "name_keywords": ["chip", "tag", "badge", "filter", "pill"],
            "node_types":    ["FRAME"],
            "height_range":  [28, 40],
            "max_width":     160,
            "notes": "Small rounded frame (28–40px tall), label + optional icon.",
        },
    },
    {
        "name":             "FAB",
        "category":         "action",
        "description":      "The FAB represents the most important action on a screen.",
        "figma_search_name": "FAB",
        "variants": [
            {"name": "FAB",          "figma_name": "FAB/FAB"},
            {"name": "Small FAB",    "figma_name": "FAB/Small FAB"},
            {"name": "Large FAB",    "figma_name": "FAB/Large FAB"},
            {"name": "Extended FAB", "figma_name": "FAB/Extended FAB"},
        ],
        "detection": {
            "name_keywords": ["fab", "floating action", "primary action"],
            "node_types":    ["FRAME"],
            "height_range":  [40, 96],
            "max_width":     200,
            "notes": "Square/rounded frame (cornerRadius ≥ 12), contains an icon child.",
        },
    },
]
