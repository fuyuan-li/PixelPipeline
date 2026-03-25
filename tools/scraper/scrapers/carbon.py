"""
Scraper for IBM Carbon Design System tokens.

Primary sources:
  carbon-design-system/carbon
    - packages/themes/src/white.js          (theme colors)
    - packages/colors/src/colors.js         (resolved color constants)
    - packages/layout/src/index.js          (spacing/container/size/icon-size)
    - packages/layout/src/tokens.js         (layout token list)
    - packages/type/scss/_styles.scss       (typography maps)
    - packages/type/src/scale.js            (resolved type scale)
    - packages/type/src/fontWeight.js       (resolved font weights)
    - packages/type/src/fontFamily.js       (resolved font families)

Fallback:
  Curated Carbon white theme colors + spacing + typography when GitHub is unavailable.
"""

import re
import requests

GITHUB_RAW = "https://raw.githubusercontent.com/carbon-design-system/carbon/main"
TIMEOUT = 15

WHITE_THEME_URL = f"{GITHUB_RAW}/packages/themes/src/white.js"
COLORS_JS_URL = f"{GITHUB_RAW}/packages/colors/src/colors.js"
LAYOUT_INDEX_URL = f"{GITHUB_RAW}/packages/layout/src/index.js"
LAYOUT_TOKENS_URL = f"{GITHUB_RAW}/packages/layout/src/tokens.js"
TYPE_STYLES_URL = f"{GITHUB_RAW}/packages/type/scss/_styles.scss"
TYPE_SCALE_URL = f"{GITHUB_RAW}/packages/type/src/scale.js"
TYPE_FONT_WEIGHT_URL = f"{GITHUB_RAW}/packages/type/src/fontWeight.js"
TYPE_FONT_FAMILY_URL = f"{GITHUB_RAW}/packages/type/src/fontFamily.js"

# ── Fallback: Carbon White theme ──────────────────────────────────────────────
# Source: https://carbondesignsystem.com/elements/color/tokens/
FALLBACK_COLORS = {
    "background":            "#ffffff",
    "background-active":     "#c6c6c6",
    "background-hover":      "#e8e8e8",
    "background-selected":   "#e0e0e0",
    "background-inverse":    "#393939",
    "layer-01":              "#f4f4f4",
    "layer-02":              "#ffffff",
    "layer-03":              "#f4f4f4",
    "layer-active-01":       "#c6c6c6",
    "layer-hover-01":        "#e8e8e8",
    "layer-selected-01":     "#e0e0e0",
    "border-subtle-00":      "#e0e0e0",
    "border-subtle-01":      "#c6c6c6",
    "border-strong-01":      "#8d8d8d",
    "border-inverse":        "#161616",
    "border-interactive":    "#0f62fe",
    "text-primary":          "#161616",
    "text-secondary":        "#525252",
    "text-placeholder":      "#a8a8a8",
    "text-disabled":         "#c6c6c6",
    "text-inverse":          "#ffffff",
    "text-on-color":         "#ffffff",
    "text-error":            "#da1e28",
    "link-primary":          "#0f62fe",
    "link-primary-hover":    "#0043ce",
    "link-secondary":        "#0043ce",
    "link-inverse":          "#78a9ff",
    "icon-primary":          "#161616",
    "icon-secondary":        "#525252",
    "icon-inverse":          "#ffffff",
    "icon-on-color":         "#ffffff",
    "icon-disabled":         "#c6c6c6",
    "interactive":           "#0f62fe",
    "focus":                 "#0f62fe",
    "focus-inverse":         "#ffffff",
    "highlight":             "#d0e2ff",
    "support-error":         "#da1e28",
    "support-success":       "#198038",
    "support-warning":       "#f1c21b",
    "support-info":          "#0043ce",
    "support-error-inverse": "#fa4d56",
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


def _fetch(url: str) -> str:
    resp = requests.get(url, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.text


def _format_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _rem(px: float) -> str:
    return f"{_format_number(px / 16)}rem"


def _rgba(hexcode: str, alpha: float) -> str | None:
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", hexcode):
        return None
    r = int(hexcode[1:3], 16)
    g = int(hexcode[3:5], 16)
    b = int(hexcode[5:7], 16)
    return f"rgba({r}, {g}, {b}, {_format_number(alpha)})"


def _format_carbon_name(token: str) -> str:
    result = ""
    for index, ch in enumerate(token):
        if ch.isdigit():
            result += "-" + token[index:]
            break
        if ch.isupper():
            if index > 0 and token[index - 1].isupper():
                result += ch.lower()
            else:
                result += "-" + ch.lower()
        else:
            result += ch
    return result


def _infer_group(name: str) -> str:
    for prefix in (
        "text", "icon", "link", "border", "layer", "background", "support",
        "interactive", "focus", "field", "overlay", "skeleton",
    ):
        if name.startswith(prefix):
            return prefix
    if name.startswith(("spacing", "fluid-spacing", "layout")):
        return "spacing"
    if name.startswith(("container", "size")):
        return "layout"
    if name.startswith(("caption", "label", "helper-text", "body", "code",
                        "heading", "productive", "expressive", "quotation",
                        "display", "legal", "fluid")):
        return "typography"
    return "misc"


def _parse_simple_color_constants(js_source: str) -> dict[str, str]:
    raw: dict[str, str] = {}
    for name, expr in re.findall(r"export const (\w+)\s*=\s*([^;]+);", js_source):
        expr = expr.strip()
        if expr.startswith("'") and expr.endswith("'"):
            raw[name] = expr[1:-1]
        elif re.fullmatch(r"\w+", expr):
            raw[name] = expr

    resolved: dict[str, str] = {}

    def resolve(name: str) -> str | None:
        if name in resolved:
            return resolved[name]
        expr = raw.get(name)
        if not expr:
            return None
        if expr.startswith("#"):
            resolved[name] = expr
            return expr
        if expr == name:
            return None
        value = resolve(expr)
        if value:
            resolved[name] = value
        return value

    for name in list(raw):
        resolve(name)
    return resolved


def _eval_color_expr(expr: str, env: dict[str, str]) -> str | None:
    expr = expr.strip()
    if expr.startswith("'") and expr.endswith("'"):
        return expr[1:-1]
    if re.fullmatch(r"\w+", expr):
        return env.get(expr)

    match = re.fullmatch(r"adjustAlpha\((\w+),\s*([\d.]+)\)", expr)
    if match:
        token, alpha = match.groups()
        return _rgba(env.get(token, ""), float(alpha))

    match = re.fullmatch(r"rgba\((\w+),\s*([\d.]+)\)", expr)
    if match:
        token, alpha = match.groups()
        return _rgba(env.get(token, ""), float(alpha))

    return None


def _parse_white_theme(white_js: str, colors_js: str) -> list[dict]:
    constants = _parse_simple_color_constants(colors_js)
    env = dict(constants)
    tokens = []

    for name, expr in re.findall(r"export const (\w+)\s*=\s*([^;]+);", white_js):
        value = _eval_color_expr(expr, env)
        if not value:
            continue
        env[name] = value
        tokens.append({
            "name": _format_carbon_name(name),
            "value": value,
            "type": "COLOR",
            "group": _infer_group(_format_carbon_name(name)),
        })
    return tokens


def _extract_layout_token_names(tokens_js: str) -> list[str]:
    match = re.search(r"unstable_tokens\s*=\s*\[(.*?)\]", tokens_js, re.S)
    if not match:
        return []
    return re.findall(r"'([^']+)'", match.group(1))


def _eval_layout_expr(expr: str) -> str | None:
    expr = expr.strip()
    if expr.startswith("'") and expr.endswith("'"):
        return expr[1:-1]
    if re.fullmatch(r"-?\d+(\.\d+)?", expr):
        return expr

    match = re.fullmatch(r"miniUnits\(([\d.]+)\)", expr)
    if match:
        return _rem(8 * float(match.group(1)))

    match = re.fullmatch(r"rem\(([\d.]+)\)", expr)
    if match:
        return _rem(float(match.group(1)))

    return None


def _parse_layout_tokens(index_js: str, tokens_js: str) -> list[dict]:
    names = _extract_layout_token_names(tokens_js)
    exprs = dict(re.findall(r"export const (\w+)\s*=\s*([^;]+);", index_js))
    tokens = []

    for name in names:
        expr = exprs.get(name)
        if not expr:
            continue
        value = _eval_layout_expr(expr)
        if value is None:
            continue
        slug = _format_carbon_name(name)
        tokens.append({
            "name": slug,
            "value": value,
            "type": "FLOAT",
            "group": _infer_group(slug),
        })
    return tokens


def _parse_scale(scale_js: str) -> list[int]:
    match = re.search(r"export const scale = \[(.*?)\];", scale_js, re.S)
    if not match:
        return []
    return [int(num) for num in re.findall(r"\d+", match.group(1))]


def _parse_font_weights(js: str) -> dict[str, str]:
    body = re.search(r"fontWeights\s*=\s*\{(.*?)\}", js, re.S)
    if not body:
        return {}
    return {
        name: value
        for name, value in re.findall(r"(\w+)\s*:\s*(\d+)", body.group(1))
    }


def _parse_font_families(js: str) -> dict[str, str]:
    body = re.search(r"fontFamilies\s*=\s*\{(.*?)\n\};", js, re.S)
    if not body:
        return {}
    return {
        name: value
        for name, value in re.findall(r'(\w+)\s*:\s*\n?\s*"([^"]+)"', body.group(1), re.S)
    }


def _extract_type_token_names(styles_scss: str) -> set[str]:
    return {name for name in re.findall(r"^\$([\w-]+):", styles_scss, re.M)}


def _extract_type_maps(styles_scss: str) -> dict[str, dict | str]:
    entries: dict[str, dict | str] = {}
    lines = styles_scss.splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        alias = re.match(r"^\$([\w-]+):\s*\$([\w-]+)\s*!default;$", stripped)
        if alias:
            entries[alias.group(1)] = f"${alias.group(2)}"
            i += 1
            continue

        start = re.match(r"^\$([\w-]+):\s*\($", stripped)
        if not start:
            i += 1
            continue

        name = start.group(1)
        i += 1
        props: dict[str, str] = {}
        while i < len(lines):
            line = re.sub(r"\s*//.*$", "", lines[i]).strip()
            if not line:
                i += 1
                continue
            if line.startswith(")"):
                break
            prop = re.match(r"^([\w-]+):\s*(.+?),?$", line)
            if prop:
                props[prop.group(1)] = prop.group(2).strip()
            i += 1
        entries[name] = props
        i += 1
    return entries


def _resolve_type_value(raw: str, scale: list[int], weights: dict[str, str], families: dict[str, str]) -> str | None:
    raw = raw.strip()
    match = re.fullmatch(r"scale\.type-scale\((\d+)\)", raw)
    if match:
        step = int(match.group(1))
        if 0 < step <= len(scale):
            return _rem(scale[step - 1])
        return None

    match = re.fullmatch(r"font-family\.font-weight\('([\w-]+)'\)", raw)
    if match:
        return weights.get(match.group(1))

    match = re.fullmatch(r"font-family\.font-family\('([\w-]+)'\)", raw)
    if match:
        return families.get(match.group(1))

    if raw.startswith("'") and raw.endswith("'"):
        return raw[1:-1]
    if re.fullmatch(r"-?\d+(\.\d+)?(px)?", raw):
        return raw
    return None


def _parse_typography_tokens(styles_scss: str, scale_js: str, font_weight_js: str, font_family_js: str) -> list[dict]:
    scale = _parse_scale(scale_js)
    weights = _parse_font_weights(font_weight_js)
    families = _parse_font_families(font_family_js)
    entries = _extract_type_maps(styles_scss)
    token_names = _extract_type_token_names(styles_scss)

    resolved_maps: dict[str, dict[str, str]] = {}

    def resolve(name: str) -> dict[str, str]:
        if name in resolved_maps:
            return resolved_maps[name]
        raw = entries.get(name)
        if raw is None:
            return {}
        if isinstance(raw, str) and raw.startswith("$"):
            resolved = dict(resolve(raw[1:]))
            resolved_maps[name] = resolved
            return resolved

        resolved: dict[str, str] = {}
        for prop, value in raw.items():
            parsed = _resolve_type_value(value, scale, weights, families)
            if parsed is not None:
                resolved[prop] = parsed
        resolved_maps[name] = resolved
        return resolved

    tokens = []
    for name in sorted(token_names):
        props = resolve(name)
        for prop, value in props.items():
            token_name = f"{name}-{prop}"
            tokens.append({
                "name": token_name,
                "value": value,
                "type": "STRING" if prop == "font-family" else "FLOAT",
                "group": "typography",
            })
    return tokens


def scrape():
    """Return normalized Carbon token list."""
    tokens: dict[str, dict] = {}
    source_parts = []

    try:
        color_tokens = _parse_white_theme(_fetch(WHITE_THEME_URL), _fetch(COLORS_JS_URL))
        for token in color_tokens:
            tokens[token["name"]] = token
        if color_tokens:
            source_parts.append("white-theme colors (GitHub)")
    except Exception:
        for name, value in FALLBACK_COLORS.items():
            tokens[name] = {"name": name, "value": value, "type": "COLOR", "group": _infer_group(name)}
        source_parts.append("fallback colors")

    try:
        layout_tokens = _parse_layout_tokens(_fetch(LAYOUT_INDEX_URL), _fetch(LAYOUT_TOKENS_URL))
        for token in layout_tokens:
            tokens[token["name"]] = token
        if layout_tokens:
            source_parts.append("layout tokens (GitHub)")
    except Exception:
        for name, value in FALLBACK_SPACING.items():
            tokens[name] = {"name": name, "value": value, "type": "FLOAT", "group": "spacing"}
        source_parts.append("fallback spacing")

    try:
        type_tokens = _parse_typography_tokens(
            _fetch(TYPE_STYLES_URL),
            _fetch(TYPE_SCALE_URL),
            _fetch(TYPE_FONT_WEIGHT_URL),
            _fetch(TYPE_FONT_FAMILY_URL),
        )
        for token in type_tokens:
            tokens[token["name"]] = token
        if type_tokens:
            source_parts.append("type tokens (GitHub)")
    except Exception:
        for name, value in FALLBACK_TYPOGRAPHY.items():
            tokens[name] = {"name": name, "value": value, "type": "FLOAT", "group": "typography"}
        source_parts.append("fallback typography")

    return {
        "system":  "Carbon Design System",
        "slug":    "carbon",
        "version": "white-theme",
        "source":  ", ".join(source_parts),
        "tokens":  sorted(tokens.values(), key=lambda token: token["name"]),
    }
