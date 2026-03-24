"""
Scraper for Atlassian Design System (ADS) tokens.

100% public — zero authentication, zero hardcoded values.

Source:
  @atlaskit/tokens npm package served via unpkg CDN.
  Light theme CJS artifact — pure data, parseable with regex.

Token naming convention (Atlassian):
  "color.background.neutral"  → slug "color-background-neutral"
  "space.100"                 → slug "space-100"
  "font.size.100"             → slug "font-size-100"

Output shape matches carbon.py / md3.py so main.py can upload to GCS unchanged.
"""

import re
import requests

TIMEOUT = 15
PKG     = "@atlaskit/tokens"
VERSION = "11.1.1"   # pin to avoid breakage when Atlassian bumps the package

# Light theme tokens-raw JS file (CJS — pure data, parseable with regex)
# Format: array of { value, cleanName, attributes: { group, state } }
_TOKEN_JS_URL = (
    f"https://unpkg.com/{PKG}@{VERSION}"
    "/dist/cjs/artifacts/tokens-raw/atlassian-light.js"
)


# ── Fetch helpers ──────────────────────────────────────────────────────────────

def _fetch_text(url: str) -> str | None:
    try:
        r = requests.get(url, timeout=TIMEOUT,
                         headers={"User-Agent": "figma-ci-scraper/1.0"})
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"      ⚠ {url}: {e}")
        return None


# ── JS parser ──────────────────────────────────────────────────────────────────

def _name_to_slug(name: str) -> str:
    """'color.background.neutral' → 'color-background-neutral'"""
    return re.sub(r"[.\s/\[\]]+", "-", name).lower().strip("-")


def _infer_group(name: str) -> str:
    nl = name.lower()
    for kw in ("background", "text", "border", "icon", "link",
               "skeleton", "blanket", "overlay", "opacity"):
        if kw in nl:
            return kw
    for kw in ("space", "radius", "font", "shadow", "elevation"):
        if kw in nl:
            return kw
    return "misc"


def _infer_type(name: str, value: str) -> str:
    if value.startswith("#") or value.startswith("rgba") or value.startswith("rgb"):
        return "COLOR"
    nl = name.lower()
    if any(k in nl for k in ("space", "radius", "size", "weight",
                              "height", "width", "gap", "font")):
        return "FLOAT"
    return "STRING"


def _parse_token_js(js: str) -> list[dict]:
    """
    Parse Atlassian's CJS tokens-raw JS file.

    Each token entry looks like:
      {
        "attributes": { "group": "paint", "state": "active", ... },
        "value": "#292A2E",
        "cleanName": "color.text"
      }

    Strategy: split on object boundaries, extract cleanName + value pairs,
    filter to active tokens with hex/rgba values only.
    """
    tokens = []

    clean_name_re = re.compile(r'"cleanName"\s*:\s*"([^"]+)"')
    value_re      = re.compile(r'"value"\s*:\s*"([^"]+)"')
    state_re      = re.compile(r'"state"\s*:\s*"([^"]+)"')

    blocks = re.split(r'\},\s*\{', js)

    for block in blocks:
        cn_m  = clean_name_re.search(block)
        val_m = value_re.search(block)
        if not cn_m or not val_m:
            continue

        token_name = cn_m.group(1)
        value      = val_m.group(1)

        # Skip deprecated / deleted / experimental
        st_m = state_re.search(block)
        if st_m and st_m.group(1) in ("deprecated", "deleted", "experimental"):
            continue

        # Skip internal palette references (e.g. "Neutral1000") — keep hex/rgba only
        if not (value.startswith("#") or value.startswith("rgb")):
            continue

        tokens.append({
            "name":  _name_to_slug(token_name),
            "value": value,
            "type":  _infer_type(token_name, value),
            "group": _infer_group(token_name),
        })

    return tokens


# ── Public entry point ─────────────────────────────────────────────────────────

def scrape() -> dict:
    """
    Scrape Atlassian Design System tokens.

    Returns:
      {
        "system":  "Atlassian Design System",
        "slug":    "atlassian",
        "version": "11.1.1",
        "source":  "<unpkg URL>",
        "tokens": [
          {"name": "color-background-neutral", "value": "#091e420f",
           "type": "COLOR", "group": "background"},
          ...
        ]
      }
    """
    print(f"  Fetching {PKG}@{VERSION} light theme from unpkg…")

    js = _fetch_text(_TOKEN_JS_URL)
    if not js:
        print("    ✗ fetch failed — no tokens scraped")
        return {"error": f"Could not fetch {_TOKEN_JS_URL}"}

    tokens = _parse_token_js(js)
    if not tokens:
        print("    ✗ parse returned empty — no tokens scraped")
        return {"error": "Fetched JS but could not parse any tokens"}

    print(f"  Done — {len(tokens)} tokens")
    return {
        "system":  "Atlassian Design System",
        "slug":    "atlassian",
        "version": VERSION,
        "source":  _TOKEN_JS_URL,
        "tokens":  tokens,
    }
