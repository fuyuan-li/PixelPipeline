"""
Scraper for Material Design 3 tokens and components.

Token source:
  material-foundation/material-tokens — JSON files following W3C design tokens spec.
  Directory listing via GitHub Contents API, then individual file fetch.

Component source:
  material-components/material-web — each component has its own directory;
  variant names are derived from the TypeScript source filenames inside each dir
  (e.g. button/filled-button.ts → variant "Filled Button").

What is scraped vs. what is statically defined:
  SCRAPED:
    - Component names (from top-level component directories)
    - Variant names (from .ts filenames inside each component directory)
    - Component descriptions (from COMPONENT_DESCRIPTIONS table — m3.material.io)

  STATIC LOOKUP TABLES (cannot be scraped — Figma/heuristic-specific):
    - COMPONENT_DIRS: maps repo dir names to canonical MD3 component names
      (e.g. "iconbutton" → "Icon Button", "list" → "List Item")
    - FIGMA_OVERRIDES: per-component Figma library data:
        figma_search_name — keyword to find the component in the Figma library
        variant_figma_names — mapping of scraped variant name → Figma path
          (e.g. "Filled Button" → "Button/Filled Button")
    - DETECTION_RULES: per-component structural inference hints used by the
      Component Classifier agent (height, width, name keywords, etc.)
"""

import re
import json
import requests

GITHUB_RAW          = "https://raw.githubusercontent.com/material-foundation/material-tokens/main"
GITHUB_API          = "https://api.github.com/repos/material-components/material-web/contents"
HEADERS             = {"User-Agent": "figma-ci-scraper/1.0"}
TIMEOUT             = 15

# DSP tokens.json: flat list of entities with type/id/value
DSP_TOKENS_URL = f"{GITHUB_RAW}/dsp/data/tokens.json"

# ── Component scraping config ──────────────────────────────────────────────────

# Top-level dirs in material-components/material-web that are NOT components.
# Everything else is treated as a component directory.
_SKIP_DIRS = {
    "catalog", "color", "docs", "elevation", "field", "focus", "icon",
    "internal", "labs", "migrations", "ripple", "sass", "scripts",
    "testing", "tokens", "typography",
}

# Per-component files whose names should NOT be treated as variant names.
# Key: component dir name. Value: set of filenames to skip.
_SKIP_FILES = {
    "chips":     {"chip-set.ts"},
    "list":      {"list.ts"},       # container, not the item component
    "tabs":      {"tabs.ts"},       # container
    "progress":  {"progress-indicator.ts"},
}

# dir_name → canonical MD3 component name.
# Only entries where auto-conversion (hyphen-split + title-case) would be wrong.
COMPONENT_DIRS = {
    "button":      "Button",
    "checkbox":    "Checkbox",
    "chips":       "Chip",
    "dialog":      "Dialog",
    "divider":     "Divider",
    "fab":         "FAB",
    "iconbutton":  "Icon Button",
    "list":        "List Item",
    "menu":        "Menu",
    "progress":    "Progress Indicator",
    "radio":       "Radio Button",
    "select":      "Select",
    "slider":      "Slider",
    "switch":      "Switch",
    "tabs":        "Tabs",
    "textfield":   "Text Field",
    "tooltip":     "Tooltip",
}

# ── Figma-specific overrides ───────────────────────────────────────────────────
# These cannot be scraped — they are specific to how the MD3 Figma community kit
# names its components and how the Component Classifier recognises raw shapes.
#
# figma_search_name   — substring to search for in Figma instance mainComponentName
# variant_figma_names — maps a scraped variant name to the exact Figma path
#                       (leave out variants that follow the default pattern)
# detection           — structural inference rules used by the classifier agent

FIGMA_OVERRIDES = {
    "Button": {
        "figma_search_name": "Button",
        "variant_figma_names": {
            "Elevated Button":     "Button/Elevated Button",
            "Filled Button":       "Button/Filled Button",
            "Filled Tonal Button": "Button/Filled Tonal Button",
            "Outlined Button":     "Button/Outlined Button",
            "Text Button":         "Button/Text Button",
        },
        "detection": {
            "name_keywords":       ["button", "btn", "cta", "action", "submit", "confirm"],
            "node_types":          ["FRAME", "RECTANGLE"],
            "height_range":        [32, 56],
            "max_width":           240,
            "requires_text_child": True,
            "notes": "Frame 32–56px tall, ≤240px wide, with a TEXT child.",
        },
    },
    "Chip": {
        "figma_search_name": "Chip",
        "variant_figma_names": {
            "Assist Chip":     "Chips/Assist chip",
            "Filter Chip":     "Chips/Filter chip",
            "Input Chip":      "Chips/Input chip",
            "Suggestion Chip": "Chips/Suggestion chip",
        },
        "detection": {
            "name_keywords": ["chip", "tag", "badge", "filter", "pill"],
            "node_types":    ["FRAME"],
            "height_range":  [28, 40],
            "max_width":     160,
            "notes": "Small rounded frame (28–40px tall), label + optional icon.",
        },
    },
    "Dialog": {
        "figma_search_name": "Dialog",
        "variant_figma_names": {},
        "detection": {
            "name_keywords": ["dialog", "modal", "alert", "popup"],
            "node_types":    ["FRAME"],
            "height_range":  [120, 560],
            "notes": "Floating frame centred on screen, contains title + actions.",
        },
    },
    "Divider": {
        "figma_search_name": "Divider",
        "variant_figma_names": {
            "Divider":        "Divider/Divider",
            "Inset Divider":  "Divider/Inset divider",
        },
        "detection": {
            "name_keywords": ["rectangle", "divider", "separator", "line", "hr"],
            "node_types":    ["RECTANGLE", "FRAME", "LINE"],
            "max_height":    4,
            "min_width":     100,
            "notes": "Thin element (height ≤ 4px, width > 100px). Raw RECTANGLE used as separator.",
        },
    },
    "FAB": {
        "figma_search_name": "FAB",
        "variant_figma_names": {
            "Fab":         "FAB/FAB",
            "Branded Fab": "FAB/Branded FAB",
        },
        "detection": {
            "name_keywords": ["fab", "floating action", "primary action"],
            "node_types":    ["FRAME"],
            "height_range":  [40, 96],
            "max_width":     200,
            "notes": "Square/rounded frame (cornerRadius ≥ 12), contains an icon child.",
        },
    },
    "Icon Button": {
        "figma_search_name": "Icon Button",
        "variant_figma_names": {},
        "detection": {
            "name_keywords": ["icon button", "icon-btn", "icon btn"],
            "node_types":    ["FRAME"],
            "height_range":  [40, 48],
            "max_width":     48,
            "notes": "Square frame (40–48px), contains a single VECTOR/icon child.",
        },
    },
    "List Item": {
        "figma_search_name": "List Item",
        "variant_figma_names": {
            "List Item": "Lists/1-line item",
        },
        "detection": {
            "name_keywords":       ["song", "track", "item", "row", "list", "entry", "music"],
            "node_types":          ["FRAME"],
            "height_range":        [48, 88],
            "min_width":           200,
            "requires_text_child": True,
            "notes": "Full-width frame (≥200px), 48–88px tall, repeating as siblings.",
        },
    },
    "Menu": {
        "figma_search_name": "Menu",
        "variant_figma_names": {},
        "detection": {
            "name_keywords": ["menu", "dropdown", "context menu"],
            "node_types":    ["FRAME"],
            "height_range":  [48, 400],
            "notes": "Floating list of options, typically with shadow/elevation.",
        },
    },
    "Navigation Bar": {
        # Note: material-web does not have a "navigationbar" dir; the component
        # is assembled from Tabs. The Figma community kit has it as Navigation Bar.
        "figma_search_name": "Navigation Bar",
        "variant_figma_names": {
            "Navigation Bar": "Navigation Bar/Navigation Bar",
        },
        "detection": {
            "name_keywords": ["nav bar", "navigation", "tab bar", "bottom nav",
                              "section 4", "navbar"],
            "node_types":    ["FRAME"],
            "height_range":  [56, 96],
            "min_width":     300,
            "notes": "Full-width frame (≥300px), 56–96px tall. 3–5 icon+label destinations.",
        },
    },
    "Progress Indicator": {
        "figma_search_name": "Progress Indicator",
        "variant_figma_names": {
            "Linear Progress Indicator":  "Progress indicators/Linear",
            "Circular Progress Indicator": "Progress indicators/Circular",
        },
        "detection": {
            "name_keywords": ["progress", "loading", "spinner"],
            "node_types":    ["FRAME"],
            "notes": "Thin horizontal bar or circular indicator.",
        },
    },
    "Radio Button": {
        "figma_search_name": "Radio Button",
        "variant_figma_names": {},
        "detection": {
            "name_keywords": ["radio", "radio button"],
            "node_types":    ["FRAME"],
            "height_range":  [40, 48],
            "max_width":     48,
            "notes": "Small circular selection control.",
        },
    },
    "Select": {
        "figma_search_name": "Select",
        "variant_figma_names": {
            "Filled Select":   "Select/Filled",
            "Outlined Select": "Select/Outlined",
        },
        "detection": {
            "name_keywords": ["select", "dropdown select", "picker"],
            "node_types":    ["FRAME"],
            "height_range":  [48, 64],
            "notes": "Form field with a trailing dropdown arrow.",
        },
    },
    "Slider": {
        "figma_search_name": "Slider",
        "variant_figma_names": {},
        "detection": {
            "name_keywords": ["slider", "range", "scrubber"],
            "node_types":    ["FRAME"],
            "height_range":  [40, 48],
            "notes": "Horizontal track with a draggable thumb.",
        },
    },
    "Switch": {
        "figma_search_name": "Switch",
        "variant_figma_names": {},
        "detection": {
            "name_keywords": ["switch", "toggle"],
            "node_types":    ["FRAME"],
            "height_range":  [28, 36],
            "max_width":     60,
            "notes": "Toggle control, wider than tall.",
        },
    },
    "Tabs": {
        "figma_search_name": "Tabs",
        "variant_figma_names": {
            "Primary Tab":   "Tabs/Primary tabs",
            "Secondary Tab": "Tabs/Secondary tabs",
        },
        "detection": {
            "name_keywords": ["tabs", "tab bar", "tab panel"],
            "node_types":    ["FRAME"],
            "height_range":  [48, 56],
            "min_width":     200,
            "notes": "Full-width horizontal tab strip.",
        },
    },
    "Text Field": {
        "figma_search_name": "Text Field",
        "variant_figma_names": {
            "Filled Text Field":   "Text fields/Filled",
            "Outlined Text Field": "Text fields/Outlined",
        },
        "detection": {
            "name_keywords": ["text field", "input", "textfield", "text input", "form field"],
            "node_types":    ["FRAME"],
            "height_range":  [48, 64],
            "notes": "Input field with label, typically has a stroke or filled background.",
        },
    },
    "Tooltip": {
        "figma_search_name": "Tooltip",
        "variant_figma_names": {},
        "detection": {
            "name_keywords": ["tooltip", "hint", "popover"],
            "node_types":    ["FRAME"],
            "height_range":  [24, 48],
            "max_width":     200,
            "notes": "Small floating label, appears on hover.",
        },
    },
    "Card": {
        # Not in material-web as a standalone component dir, but present in Figma kit.
        "figma_search_name": "Card",
        "variant_figma_names": {
            "Filled Card":   "Cards/Filled card",
            "Outlined Card": "Cards/Outlined card",
            "Elevated Card": "Cards/Elevated card",
        },
        "detection": {
            "name_keywords":     ["card", "tile", "panel"],
            "node_types":        ["FRAME"],
            "min_corner_radius": 8,
            "notes": "Frame with cornerRadius ≥ 8, containing headline text.",
        },
    },
    "Top App Bar": {
        # Not a standalone dir in material-web; present in Figma kit.
        "figma_search_name": "Top App Bar",
        "variant_figma_names": {
            "Center-aligned Top App Bar": "Top app bar/Center-aligned",
            "Small Top App Bar":          "Top app bar/Small",
            "Medium Top App Bar":         "Top app bar/Medium",
            "Large Top App Bar":          "Top app bar/Large",
        },
        "detection": {
            "name_keywords": ["top bar", "app bar", "header", "toolbar",
                              "section 1", "section 2", "section 3"],
            "node_types":    ["FRAME"],
            "height_range":  [56, 152],
            "min_width":     300,
            "notes": "Full-width frame at top of screen, 56–152px tall.",
        },
    },
}

# Components present in the Figma community kit but NOT as a dedicated dir in
# material-components/material-web (so they won't appear in the scraped list).
# Merged in after scraping.
_FIGMA_ONLY_COMPONENTS = ["Card", "Top App Bar", "Navigation Bar"]

# Descriptions sourced from m3.material.io/components (stable copy — changes rarely).
COMPONENT_DESCRIPTIONS = {
    "Button":             "Buttons help people initiate actions, from sending an email to deleting a document.",
    "Checkbox":           "Checkboxes let users select one or more items from a list.",
    "Chip":               "Chips help people enter information, make selections, filter content, or trigger actions.",
    "Dialog":             "Dialogs provide important prompts in a user flow.",
    "Divider":            "Dividers are thin lines that group content in lists and layouts.",
    "FAB":                "The FAB represents the most important action on a screen.",
    "Icon Button":        "Icon buttons help people take supplementary actions with a single tap.",
    "List Item":          "Lists are continuous, vertical indexes of text or images.",
    "Menu":               "Menus display a list of choices on a temporary surface.",
    "Navigation Bar":     "Navigation bars offer a persistent and convenient way to switch between primary destinations.",
    "Progress Indicator": "Progress indicators show the status of a process in real time.",
    "Radio Button":       "Radio buttons let people select one option from a set.",
    "Select":             "Select menus display a list of choices on a temporary surface and display the currently selected menu item above the list.",
    "Slider":             "Sliders allow users to make selections from a range of values.",
    "Switch":             "Switches toggle the state of a single item on or off.",
    "Tabs":               "Tabs organize content across different screens, data sets, and other interactions.",
    "Text Field":         "Text fields let users enter text into a UI.",
    "Tooltip":            "Tooltips display brief labels or messages.",
    "Card":               "Cards contain content and actions about a single subject.",
    "Top App Bar":        "Top app bars display navigation and actions relating to the current screen.",
    "Checkbox":           "Checkboxes let users select one or more items from a list.",
}

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


def _scrape_component_dirs():
    """
    List all component directories from material-components/material-web.
    Returns a dict of {dir_name: [variant_ts_filenames]} for known component dirs.
    Falls back to an empty dict if GitHub is unreachable.
    """
    try:
        resp = requests.get(GITHUB_API, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        top_level = {item["name"] for item in resp.json() if item["type"] == "dir"}
    except Exception:
        return {}

    component_dirs = {}
    for dir_name in sorted(top_level - _SKIP_DIRS):
        if dir_name not in COMPONENT_DIRS:
            continue  # only include dirs we have a name mapping for
        try:
            resp = requests.get(f"{GITHUB_API}/{dir_name}", headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            skip = _SKIP_FILES.get(dir_name, set())
            ts_files = [
                item["name"]
                for item in resp.json()
                if item["type"] == "file"
                and item["name"].endswith(".ts")
                and not item["name"].endswith("_test.ts")
                and item["name"] not in skip
                and item["name"] not in {"harness.ts", "index.ts"}
                and "internal" not in item.get("path", "")
            ]
            component_dirs[dir_name] = ts_files
        except Exception:
            component_dirs[dir_name] = []

    return component_dirs


def _ts_filename_to_variant_name(filename: str) -> str:
    """Convert a TypeScript filename to a human-readable variant name.
    e.g. 'filled-button.ts' → 'Filled Button'
         'branded-fab.ts'   → 'Branded Fab'
    """
    stem = filename.replace(".ts", "")
    return " ".join(word.capitalize() for word in stem.split("-"))


def _build_component_catalog(scraped_dirs: dict) -> list:
    """
    Build the component catalog by merging scraped GitHub data with the
    FIGMA_OVERRIDES and COMPONENT_DESCRIPTIONS lookup tables.
    """
    components = []
    seen = set()

    # ── Components discovered by scraping ────────────────────────────────────
    for dir_name, ts_files in scraped_dirs.items():
        comp_name = COMPONENT_DIRS[dir_name]
        if comp_name in seen:
            continue
        seen.add(comp_name)

        overrides = FIGMA_OVERRIDES.get(comp_name, {})
        variant_figma = overrides.get("variant_figma_names", {})

        # Derive variant list from scraped .ts filenames
        variants = []
        for fname in sorted(ts_files):
            vname = _ts_filename_to_variant_name(fname)
            variants.append({
                "name":       vname,
                "figma_name": variant_figma.get(vname, f"{comp_name}/{vname}"),
            })

        # If no variants found, fall back to a single entry = the component itself
        if not variants:
            default_figma = variant_figma.get(comp_name, comp_name)
            variants = [{"name": comp_name, "figma_name": default_figma}]

        components.append({
            "name":             comp_name,
            "description":      COMPONENT_DESCRIPTIONS.get(comp_name, ""),
            "figma_search_name": overrides.get("figma_search_name", comp_name),
            "variants":         variants,
            "detection":        overrides.get("detection", {}),
        })

    # ── Figma-only components (not in material-web repo) ─────────────────────
    for comp_name in _FIGMA_ONLY_COMPONENTS:
        if comp_name in seen:
            continue
        seen.add(comp_name)
        overrides = FIGMA_OVERRIDES.get(comp_name, {})
        variant_figma = overrides.get("variant_figma_names", {})
        variants = [
            {"name": vname, "figma_name": fname}
            for vname, fname in variant_figma.items()
        ] or [{"name": comp_name, "figma_name": comp_name}]
        components.append({
            "name":             comp_name,
            "description":      COMPONENT_DESCRIPTIONS.get(comp_name, ""),
            "figma_search_name": overrides.get("figma_search_name", comp_name),
            "variants":         variants,
            "detection":        overrides.get("detection", {}),
        })

    return sorted(components, key=lambda c: c["name"])


def scrape():
    """Return normalised M3 data: component catalog (primary) + tokens (supplementary)."""

    # ── Components ────────────────────────────────────────────────────────────
    scraped_dirs = _scrape_component_dirs()
    components   = _build_component_catalog(scraped_dirs)
    comp_source  = "material-components/material-web (GitHub)" if scraped_dirs else "FIGMA_OVERRIDES fallback only"

    # ── Tokens ────────────────────────────────────────────────────────────────
    tokens = _try_github_fetch()
    token_source = "material-foundation/material-tokens (GitHub)"
    if not tokens:
        token_source = "curated fallback (GitHub unavailable)"
        for name, value in FALLBACK_COLORS.items():
            group = name.split(".")[2] if name.count(".") >= 2 else "color"
            tokens.append({"name": name, "value": value, "type": "COLOR", "group": group})
        for name, value in FALLBACK_TYPOGRAPHY.items():
            tokens.append({"name": name, "value": value, "type": "FLOAT", "group": "typography"})

    return {
        "system":         "Material Design 3",
        "slug":           "md3",
        "version":        "baseline-light",
        "component_source": comp_source,
        "token_source":   token_source,
        "components":     components,
        "tokens":         tokens,
    }
