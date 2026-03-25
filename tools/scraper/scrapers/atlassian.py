"""
Scraper for Atlassian Design System (ADS) tokens.

100% public — zero authentication, zero hardcoded values.

Source:
  @atlaskit/tokens npm package served via unpkg CDN.
  Tokens are split across multiple CJS artifacts:
    - atlassian-light.js       (theme colors/elevation)
    - atlassian-shape.js       (corner radius / shape)
    - atlassian-spacing.js     (spacing scale)
    - atlassian-typography.js  (font + typescale)

Token naming convention (Atlassian):
  "color.background.neutral"  → slug "color-background-neutral"
  "space.100"                 → slug "space-100"
  "font.size.100"             → slug "font-size-100"
  "corner.radius.100"         → slug "corner-radius-100"

Output shape matches carbon.py / md3.py so main.py can upload to GCS unchanged.
"""

import re
import requests

TIMEOUT = 15
PKG     = "@atlaskit/tokens"
VERSION = "11.1.1"   # pin to avoid breakage when Atlassian bumps the package

# Tokens-raw JS files (CJS — pure data, parseable with regex)
# Format: array of { value, cleanName, attributes: { group, state } }
_TOKEN_JS_URLS = {
    "light": (
        f"https://unpkg.com/{PKG}@{VERSION}"
        "/dist/cjs/artifacts/tokens-raw/atlassian-light.js"
    ),
    "shape": (
        f"https://unpkg.com/{PKG}@{VERSION}"
        "/dist/cjs/artifacts/tokens-raw/atlassian-shape.js"
    ),
    "spacing": (
        f"https://unpkg.com/{PKG}@{VERSION}"
        "/dist/cjs/artifacts/tokens-raw/atlassian-spacing.js"
    ),
    "typography": (
        f"https://unpkg.com/{PKG}@{VERSION}"
        "/dist/cjs/artifacts/tokens-raw/atlassian-typography.js"
    ),
}
_TOKENS_RAW_SOURCE = f"https://unpkg.com/{PKG}@{VERSION}/dist/cjs/artifacts/tokens-raw/"


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
    for kw in ("space", "spacing", "radius", "corner", "shape",
               "font", "typography", "shadow", "elevation"):
        if kw in nl:
            return kw
    return "misc"


def _infer_type(name: str, value: str) -> str:
    if value.startswith("#") or value.startswith("rgba") or value.startswith("rgb"):
        return "COLOR"
    nl = name.lower()
    if "font.family" in nl or "fontfamily" in nl:
        return "STRING"
    if re.fullmatch(r"-?\d+(\.\d+)?([a-z%]+)?", value.strip().lower()):
        return "FLOAT"
    if any(k in nl for k in ("space", "radius", "size", "weight",
                              "height", "width", "gap", "font", "corner", "shape")):
        return "FLOAT"
    return "STRING"


def _extract_value(block: str) -> str | None:
    """
    Extract a JSON-like primitive value from a token block.

    Supports:
      "value": "#FFFFFF"
      "value": "4px"
      "value": 4
      "value": 1.5
    """
    match = re.search(
        r'"value"\s*:\s*(?:"([^"]*)"|(-?\d+(?:\.\d+)?))',
        block,
    )
    if not match:
        return None
    return match.group(1) if match.group(1) is not None else match.group(2)


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
    keep active stable token values across color/shape/spacing/typography.
    """
    tokens = []

    clean_name_re = re.compile(r'"cleanName"\s*:\s*"([^"]+)"')
    state_re      = re.compile(r'"state"\s*:\s*"([^"]+)"')

    blocks = re.split(r'\},\s*\{', js)

    for block in blocks:
        cn_m  = clean_name_re.search(block)
        value = _extract_value(block)
        if not cn_m or value is None:
            continue

        token_name = cn_m.group(1)

        # Skip deprecated / deleted / experimental
        st_m = state_re.search(block)
        if st_m and st_m.group(1) in ("deprecated", "deleted", "experimental"):
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
    print(f"  Fetching {PKG}@{VERSION} token artifacts from unpkg…")

    merged: dict[str, dict] = {}
    fetched_any = False

    for label, url in _TOKEN_JS_URLS.items():
        js = _fetch_text(url)
        if not js:
            continue
        fetched_any = True
        parsed = _parse_token_js(js)
        for token in parsed:
            merged[token["name"]] = token
        print(f"    ✓ {label:10s} {len(parsed):4d} tokens")

    if not fetched_any:
        print("    ✗ fetch failed — no tokens scraped")
        return {"error": f"Could not fetch Atlassian token artifacts from {_TOKENS_RAW_SOURCE}"}

    tokens = sorted(merged.values(), key=lambda token: token["name"])
    if not tokens:
        print("    ✗ parse returned empty — no tokens scraped")
        return {"error": "Fetched Atlassian JS artifacts but could not parse any tokens"}

    print(f"  Done — {len(tokens)} unique tokens")
    return {
        "system":  "Atlassian Design System",
        "slug":    "atlassian",
        "version": VERSION,
        "source":  _TOKENS_RAW_SOURCE,
        "tokens":  tokens,
    }
