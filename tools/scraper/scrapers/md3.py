"""
Scraper for Material Design 3 component specs.

100% scraped from GitHub — zero hardcoded design values.

Source: material-components/material-web
  tokens/versions/v30_0/sass/

Resolution chain:
  _md-ref-palette.scss     → baseline hex values  (e.g. $primary40: #6750a4)
  _md-ref-typeface.scss    → font family strings  (e.g. $plain: Roboto)
  _md-sys-color.scss       → color tokens         (e.g. $primary: md-ref-palette.$primary40)
  _md-sys-typescale.scss   → typography tokens    (e.g. $label-large-size: 0.875rem)
  _md-sys-shape.scss       → shape tokens         (e.g. $corner-full: 9999px)
  _md-sys-elevation.scss   → elevation tokens
  _md-sys-state.scss       → state-layer tokens
  _md-comp-*.scss          → per-component specs  (e.g. $container-color: md-sys-color.$primary)

Each component entry in the output has:
  id      — machine id (e.g. "md.comp.button-filled")
  name    — human name (e.g. "Button Filled")
  tokens  — dict of resolved token values for the enabled/default state
             color values are hex strings, sizes in rem/px, weights as numbers
"""

import re
import requests

GITHUB_RAW = "https://raw.githubusercontent.com/material-components/material-web/main"
GITHUB_API = "https://api.github.com/repos/material-components/material-web/contents"
SASS_PATH  = "tokens/versions/v30_0/sass"
HEADERS    = {"User-Agent": "figma-ci-scraper/1.0"}
TIMEOUT    = 15

# Resolution source files, in dependency order (palette before sys-color, etc.)
_RESOLUTION_FILES = [
    ("md-ref-palette",   "_md-ref-palette.scss"),
    ("md-ref-typeface",  "_md-ref-typeface.scss"),
    ("md-sys-color",     "_md-sys-color.scss"),
    ("md-sys-typescale", "_md-sys-typescale.scss"),
    ("md-sys-shape",     "_md-sys-shape.scss"),
    ("md-sys-elevation", "_md-sys-elevation.scss"),
    ("md-sys-state",     "_md-sys-state.scss"),
]

# Interaction / non-default state prefixes to exclude from component specs.
# We only want the default (enabled) state values.
_STATE_PREFIXES = (
    "hover-", "focus-", "pressed-", "dragged-",
    "disabled-", "error-", "selected-",
    # logical shape sub-tokens (we keep the main container-shape)
    "container-shape-start-", "container-shape-end-",
)


# ── Fetch helpers ──────────────────────────────────────────────────────────────

def _fetch(path: str) -> str:
    try:
        r = requests.get(f"{GITHUB_RAW}/{path}", headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"    ⚠ fetch failed {path}: {e}")
        return ""


def _list_sass_files() -> list[str]:
    try:
        r = requests.get(f"{GITHUB_API}/{SASS_PATH}", headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        return [item["name"] for item in r.json() if item["type"] == "file"]
    except Exception as e:
        print(f"    ⚠ could not list sass dir: {e}")
        return []


# ── SCSS parsing ───────────────────────────────────────────────────────────────

def _parse_vars(content: str) -> dict[str, str]:
    """
    Extract all top-level SCSS variable assignments from file content.
    Returns {var_name: raw_value_string}.

    Handles:
      $primary40: #6750a4;
      $primary: md-ref-palette.$primary40;
      $label-large-size: 0.875rem;
      $corner-full: 9999px;
    """
    result = {}
    for line in content.splitlines():
        line = line.strip()
        if not line.startswith("$"):
            continue
        # Strip inline comments
        line = re.sub(r"\s*//.*$", "", line).strip()
        line = line.rstrip(";").strip()
        if ":" not in line:
            continue
        name, _, value = line.partition(":")
        name  = name.strip().lstrip("$")
        value = value.strip()
        # Skip empty, null, or complex SCSS expressions (function calls, maps, etc.)
        if not name or not value or value == "null":
            continue
        if "(" in value or "{" in value:
            continue
        result[name] = value
    return result


def _resolve(raw: str, maps: dict[str, dict]) -> str | None:
    """
    Resolve a SCSS value to its final string.

    'md-sys-color.$primary'     → looks up maps['md-sys-color']['primary']
    'md-ref-palette.$primary40' → looks up maps['md-ref-palette']['primary40']
    '#6750a4'                   → returned as-is
    '40px', '0.875rem', '500'   → returned as-is
    'Roboto'                    → returned as-is
    """
    if not raw:
        return None
    # Pattern: module.$varname
    m = re.fullmatch(r"([\w-]+)\.\$([\w-]+)", raw)
    if m:
        module, var = m.group(1), m.group(2)
        if module in maps and var in maps[module]:
            return maps[module][var]
        return None   # unresolvable reference — omit
    return raw


# ── Resolution map builder ─────────────────────────────────────────────────────

def _build_resolution_maps(available_files: set[str]) -> dict[str, dict]:
    """
    Fetch and parse all sys/ref token files.
    Returns {module_name: {var_name: resolved_value}}.
    Each module is fully resolved before the next one is parsed,
    so cross-module references work (e.g. sys-color → ref-palette).
    """
    maps: dict[str, dict] = {}

    for module_name, filename in _RESOLUTION_FILES:
        if filename not in available_files:
            print(f"    ⚠ {filename} not found — skipping")
            continue

        print(f"    Loading {filename}…")
        raw_vars = _parse_vars(_fetch(f"{SASS_PATH}/{filename}"))
        resolved: dict[str, str] = {}
        for var, raw in raw_vars.items():
            val = _resolve(raw, maps)
            if val is not None:
                resolved[var] = val
        maps[module_name] = resolved
        print(f"      → {len(resolved)} vars resolved")

    return maps


# ── Component file parser ──────────────────────────────────────────────────────

def _parse_component(content: str, maps: dict[str, dict]) -> dict[str, str]:
    """
    Parse a _md-comp-*.scss file and return a dict of resolved token values
    for the default (enabled) state only.
    """
    raw_vars = _parse_vars(content)
    tokens: dict[str, str] = {}
    for name, raw in raw_vars.items():
        # Skip interaction / non-default states
        if any(name.startswith(p) for p in _STATE_PREFIXES):
            continue
        val = _resolve(raw, maps)
        if val is not None:
            tokens[name] = val
    return tokens


def _filename_to_id_and_name(filename: str) -> tuple[str, str]:
    """
    '_md-comp-button-filled.scss' → ('md.comp.button-filled', 'Button Filled')
    """
    stem = filename.removeprefix("_md-comp-").removesuffix(".scss")
    name = " ".join(w.capitalize() for w in stem.split("-"))
    return f"md.comp.{stem}", name


# ── Public entry point ─────────────────────────────────────────────────────────

def scrape() -> dict:
    """
    Scrape the complete MD3 component catalog from material-components/material-web.

    Returns:
      {
        "system": "Material Design 3",
        "slug": "md3",
        "version": "30.0",
        "source": "<GitHub path>",
        "components": [
          {
            "id":     "md.comp.button-filled",
            "name":   "Button Filled",
            "tokens": {
              "container-color":    "#6750a4",
              "container-height":   "40px",
              "container-shape":    "9999px",
              "label-text-size":    "0.875rem",
              "label-text-weight":  "500",
              "leading-space":      "24px",
              ...
            }
          },
          ...
        ]
      }
    """
    print("  Listing sass directory…")
    all_files = _list_sass_files()
    if not all_files:
        return {"error": "Could not list sass directory from GitHub"}

    available = set(all_files)
    print(f"  Found {len(all_files)} files total.\n  Building token resolution maps…")
    maps = _build_resolution_maps(available)

    comp_files = sorted(f for f in all_files
                        if f.startswith("_md-comp-") and f.endswith(".scss"))
    print(f"\n  Scraping {len(comp_files)} component files…")

    components = []
    for filename in comp_files:
        comp_id, comp_name = _filename_to_id_and_name(filename)
        content = _fetch(f"{SASS_PATH}/{filename}")
        if not content:
            continue
        tokens = _parse_component(content, maps)
        if not tokens:
            continue
        components.append({
            "id":     comp_id,
            "name":   comp_name,
            "tokens": tokens,
        })
        print(f"    ✓ {comp_name:45s} {len(tokens):3d} tokens")

    print(f"\n  Done — {len(components)} components scraped.")
    return {
        "system":     "Material Design 3",
        "slug":       "md3",
        "version":    "30.0",
        "source":     f"{GITHUB_RAW}/{SASS_PATH}",
        "components": components,
    }
