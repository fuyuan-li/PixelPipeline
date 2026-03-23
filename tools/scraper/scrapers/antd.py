"""
Scraper for Ant Design v5 tokens.

Primary source:
  ant-design/ant-design — token-meta.json (generated metadata listing all design tokens
  with their default values, types, and descriptions).
  URL: https://raw.githubusercontent.com/ant-design/ant-design/master/token-meta.json

Fallback:
  Curated Ant Design v5 seed + global tokens (the foundational set).
"""

import json
import requests

GITHUB_RAW = "https://raw.githubusercontent.com/ant-design/ant-design/master"
TIMEOUT    = 15

# ── Fallback: Ant Design v5 core tokens ───────────────────────────────────────
# Source: https://ant.design/docs/react/customize-theme
FALLBACK_COLORS = {
    # Brand
    "colorPrimary":           "#1677ff",
    "colorSuccess":           "#52c41a",
    "colorWarning":           "#faad14",
    "colorError":             "#ff4d4f",
    "colorInfo":              "#1677ff",
    # Text
    "colorTextBase":          "#000000",
    "colorText":              "#000000e0",
    "colorTextSecondary":     "#00000073",
    "colorTextTertiary":      "#00000045",
    "colorTextQuaternary":    "#0000001f",
    # Background
    "colorBgBase":            "#ffffff",
    "colorBgContainer":       "#ffffff",
    "colorBgElevated":        "#ffffff",
    "colorBgLayout":          "#f5f5f5",
    "colorBgSpotlight":       "#000000",
    # Border
    "colorBorder":            "#d9d9d9",
    "colorBorderSecondary":   "#f0f0f0",
    # Fill
    "colorFill":              "#0000001a",
    "colorFillSecondary":     "#0000000f",
    "colorFillTertiary":      "#0000000a",
    "colorFillQuaternary":    "#00000005",
    # Primary palette
    "blue-1":  "#e6f4ff",
    "blue-2":  "#bae0ff",
    "blue-3":  "#91caff",
    "blue-4":  "#69b1ff",
    "blue-5":  "#4096ff",
    "blue-6":  "#1677ff",
    "blue-7":  "#0958d9",
    "blue-8":  "#003eb3",
    "blue-9":  "#002c8c",
    "blue-10": "#001d66",
}

FALLBACK_TYPOGRAPHY = {
    "fontSize":    "14",
    "fontSizeSM":  "12",
    "fontSizeLG":  "16",
    "fontSizeXL":  "20",
    "fontSizeHeading1": "38",
    "fontSizeHeading2": "30",
    "fontSizeHeading3": "24",
    "fontSizeHeading4": "20",
    "fontSizeHeading5": "16",
    "lineHeight":   "1.5714285714285714",
}

FALLBACK_SPACING = {
    "marginXXS":  "4",
    "marginXS":   "8",
    "marginSM":   "12",
    "margin":     "16",
    "marginMD":   "20",
    "marginLG":   "24",
    "marginXL":   "32",
    "marginXXL":  "48",
    "paddingXXS": "4",
    "paddingXS":  "8",
    "paddingSM":  "12",
    "padding":    "16",
    "paddingMD":  "20",
    "paddingLG":  "24",
    "paddingXL":  "32",
    "borderRadius":   "6",
    "borderRadiusLG": "8",
    "borderRadiusSM": "4",
    "borderRadiusXS": "2",
}


def _parse_token_meta(meta):
    """Parse Ant Design's token-meta.json format."""
    tokens = []
    for token_name, info in meta.items():
        if not isinstance(info, dict):
            continue
        value     = info.get("defaultValue", "")
        type_hint = info.get("type", "")

        if isinstance(value, bool):
            tok_type = "BOOLEAN"
            value    = str(value).lower()
        elif isinstance(value, (int, float)):
            tok_type = "FLOAT"
            value    = str(value)
        elif isinstance(value, str) and (value.startswith("#") or value.startswith("rgb")):
            tok_type = "COLOR"
        else:
            tok_type = "STRING"
            value    = str(value)

        if value in ("", "undefined", "null"):
            continue

        tokens.append({
            "name":  token_name,
            "value": value,
            "type":  tok_type,
            "group": info.get("source", "global"),
        })
    return tokens


def _try_github_fetch():
    """Try to fetch token-meta.json from Ant Design's repo."""
    try:
        resp = requests.get(f"{GITHUB_RAW}/token-meta.json", timeout=15)
        resp.raise_for_status()
        meta = resp.json()
        tokens = _parse_token_meta(meta)
        if tokens:
            return tokens
    except Exception:
        pass
    return []


def scrape():
    """Return normalised Ant Design token list."""
    tokens = _try_github_fetch()

    if not tokens:
        for name, value in FALLBACK_COLORS.items():
            tokens.append({"name": name, "value": value, "type": "COLOR", "group": "color"})
        for name, value in FALLBACK_TYPOGRAPHY.items():
            tokens.append({"name": name, "value": value, "type": "FLOAT", "group": "typography"})
        for name, value in FALLBACK_SPACING.items():
            tokens.append({"name": name, "value": value, "type": "FLOAT", "group": "spacing"})

    return {
        "system":  "Ant Design",
        "slug":    "antd",
        "version": "v5",
        "source":  "ant-design/ant-design token-meta.json (GitHub) or curated fallback",
        "tokens":  tokens,
    }
