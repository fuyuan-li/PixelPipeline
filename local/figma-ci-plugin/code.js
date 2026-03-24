// code.js runs inside the Figma sandbox — no network access here.
// All GitLab API calls happen in ui.html (the iframe), which can use fetch().
// This file handles: showing the UI, reading Figma data, persisting settings,
// and applying fixes received from the Fix Agent via ui.html.

figma.showUI(__html__, { width: 440, height: 520 });

// On startup, load saved settings and fetch available design system libraries.
async function init() {
  const [
    projectPath,
    baseBranch,
    token,
    lastReviewBranch,
    lastMrIid,
    savedLibraryName,
  ] = await Promise.all([
    figma.clientStorage.getAsync('projectPath'),
    figma.clientStorage.getAsync('baseBranch'),
    figma.clientStorage.getAsync('token'),
    figma.clientStorage.getAsync('lastReviewBranch'),
    figma.clientStorage.getAsync('lastMrIid'),
    figma.clientStorage.getAsync('selectedLibraryName'),
  ]);

  figma.ui.postMessage({
    type: 'init',
    settings: {
      projectPath:       projectPath       || '',
      baseBranch:        baseBranch        || 'main',
      token:             token             || '',
      lastReviewBranch:  lastReviewBranch  || '',
      lastMrIid:         lastMrIid         || '',
      savedLibraryName:  savedLibraryName  || '',
    },
  });

  // Fetch available libraries for the dropdown.
  // Small delay to ensure the UI iframe is ready to receive messages.
  await new Promise(r => setTimeout(r, 300));
  figma.ui.postMessage({
    type: 'available-libraries',
    libraries: await getAvailableLibraries(),
  });
}

init();

// ─── hex ↔ Figma RGBA helpers ──────────────────────────────────────────────

function hexToFigmaRgb(hex) {
  const clean = hex.replace('#', '');
  const full  = clean.length === 3
    ? clean.split('').map(c => c + c).join('')
    : clean;
  return {
    r: parseInt(full.slice(0, 2), 16) / 255,
    g: parseInt(full.slice(2, 4), 16) / 255,
    b: parseInt(full.slice(4, 6), 16) / 255,
  };
}

function normalizeHexColor(value) {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  const withHash = trimmed.startsWith('#') ? trimmed : `#${trimmed}`;
  const clean = withHash.replace('#', '');
  if (!/^[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$/.test(clean)) return null;
  return `#${clean.toUpperCase()}`;
}

function normalizeNumber(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value !== 'string') return null;

  const trimmed = value.trim().toLowerCase();
  if (!trimmed) return null;

  if (/^-?\d+(\.\d+)?px$/.test(trimmed)) {
    return parseFloat(trimmed.replace('px', ''));
  }
  if (/^-?\d+(\.\d+)?rem$/.test(trimmed)) {
    return parseFloat(trimmed.replace('rem', '')) * 16;
  }
  if (/^-?\d+(\.\d+)?$/.test(trimmed)) {
    return parseFloat(trimmed);
  }
  return null;
}

function clonePaintArray(paints) {
  return JSON.parse(JSON.stringify(Array.isArray(paints) ? paints : []));
}

function buildSolidPaint(basePaint, hex) {
  return Object.assign({}, basePaint || {}, {
    type: 'SOLID',
    visible: basePaint && basePaint.visible !== undefined ? basePaint.visible : true,
    opacity: basePaint && basePaint.opacity !== undefined ? basePaint.opacity : 1,
    blendMode: basePaint && basePaint.blendMode ? basePaint.blendMode : 'NORMAL',
    color: hexToFigmaRgb(hex),
  });
}

function setPaintColor(node, prop, targetValue, fillIndex) {
  if (!(prop in node)) return { ok: false, status: 'unsupported_property' };

  const hex = normalizeHexColor(targetValue);
  if (!hex) return { ok: false, status: 'invalid_value' };

  const paints = clonePaintArray(node[prop]);
  const idx = typeof fillIndex === 'number' ? fillIndex : 0;

  if (!paints[idx]) {
    if (idx !== 0) return { ok: false, status: 'fill_index_missing' };
    paints[idx] = buildSolidPaint(null, hex);
  } else {
    paints[idx] = buildSolidPaint(paints[idx], hex);
  }

  node[prop] = paints;
  return { ok: true };
}

async function loadTextNodeFontAsync(node) {
  if (!node || node.type !== 'TEXT') return;
  if (node.fontName === figma.mixed || typeof node.fontName === 'symbol') return;
  await figma.loadFontAsync(node.fontName);
}

function resizeNode(node, widthValue, heightValue) {
  if (!('resize' in node)) return { ok: false, status: 'unsupported_property' };

  const width  = widthValue  != null ? normalizeNumber(widthValue)  : node.width;
  const height = heightValue != null ? normalizeNumber(heightValue) : node.height;

  if (width == null || height == null) {
    return { ok: false, status: 'invalid_value' };
  }

  node.resize(width, height);
  return { ok: true };
}

// ─── message handler ───────────────────────────────────────────────────────

figma.ui.onmessage = async (msg) => {

  // Persist settings.
  if (msg.type === 'save-settings') {
    const s = msg.settings;
    await figma.clientStorage.setAsync('projectPath',        s.projectPath);
    await figma.clientStorage.setAsync('baseBranch',         s.baseBranch);
    await figma.clientStorage.setAsync('selectedLibraryName', s.selectedLibraryName || '');
    if (s.rememberToken && s.token) {
      await figma.clientStorage.setAsync('token', s.token);
    } else {
      await figma.clientStorage.deleteAsync('token');
    }
  }

  // After a successful MR creation, persist the branch + MR IID for the Apply tab.
  if (msg.type === 'save-review-ref') {
    await figma.clientStorage.setAsync('lastReviewBranch', msg.branch);
    await figma.clientStorage.setAsync('lastMrIid',        String(msg.mrIid));
  }

  // Export the current selection (or whole page) as JSON for GitLab.
  // Also fetches variables from the selected design system library.
  if (msg.type === 'get-figma-export') {
    try {
      const page      = figma.currentPage;
      const selection = figma.currentPage.selection;
      const targets   = selection.length > 0 ? [...selection] : [page];

      // Fetch variables from the selected library collection.
      let designSystem = null;
      if (msg.selectedLibrary) {
        const lib = msg.selectedLibrary;
        // slug comes pre-resolved from ui.html's DESIGN_SYSTEM_SLUG_MAP.
        // Pass it through so the Flow can call the design-tokens API directly
        // without guessing, while still having the human-readable name for review text.
        const slug = lib.slug !== undefined && lib.slug !== null ? lib.slug : null;
        if (lib.key) {
          // Variable collection — we can fetch token names.
          try {
            const libVars = await figma.teamLibrary.getVariablesInLibraryCollectionAsync(lib.key);
            designSystem = {
              name:           lib.libraryName,
              slug:           slug,
              collectionName: lib.name,
              type:           'variables',
              variables: libVars.map(v => ({
                key:          v.key,
                name:         v.name,
                resolvedType: v.resolvedType, // 'COLOR' | 'FLOAT' | 'STRING' | 'BOOLEAN'
              })),
            };
          } catch (libErr) {
            designSystem = {
              name:      lib.libraryName,
              slug:      slug,
              type:      'variables',
              error:     libErr.message,
              variables: [],
            };
          }
        } else {
          // Component-only library (no published variable collection).
          // No token list available; the auditor will rely on boundVariables
          // and mainComponentName instead.
          designSystem = {
            name:           lib.libraryName,
            slug:           slug,
            collectionName: lib.name,
            type:           'components',
            variables:      [],
          };
        }
      }

      const payload = {
        exportedAt:   new Date().toISOString(),
        designSystem,
        document: {
          pageId:   page.id,
          pageName: page.name,
        },
        nodes: targets.map(serializeNode),
      };

      figma.ui.postMessage({ type: 'figma-export', payload });
    } catch (err) {
      figma.ui.postMessage({ type: 'export-error', message: err.message });
    }
  }

  // Apply a list of fixes produced by the Fix Agent.
  if (msg.type === 'apply-fixes') {
    const results = [];

    for (const fix of msg.fixes) {
      const node = figma.getNodeById(fix.target_node_id || fix.node_id);

      if (!node) {
        results.push(Object.assign({}, fix, { status: 'not_found' }));
        continue;
      }

      try {
        if (fix.property === 'fills' || fix.property === 'strokes') {
          const outcome = setPaintColor(node, fix.property, fix.target_value, fix.fill_index);
          results.push(Object.assign({}, fix, { status: outcome.ok ? 'applied' : outcome.status }));

        } else if (fix.property === 'textColor') {
          if (node.type !== 'TEXT') {
            results.push(Object.assign({}, fix, { status: 'unsupported_property' }));
            continue;
          }
          const outcome = setPaintColor(node, 'fills', fix.target_value, 0);
          results.push(Object.assign({}, fix, { status: outcome.ok ? 'applied' : outcome.status }));

        } else if (fix.property === 'fontSize' && 'fontSize' in node) {
          const fontSize = normalizeNumber(fix.target_value);
          if (fontSize == null) {
            results.push(Object.assign({}, fix, { status: 'invalid_value' }));
            continue;
          }
          await loadTextNodeFontAsync(node);
          node.fontSize = fontSize;
          results.push(Object.assign({}, fix, { status: 'applied' }));

        } else if (fix.property === 'cornerRadius' && 'cornerRadius' in node) {
          const cornerRadius = normalizeNumber(fix.target_value);
          if (cornerRadius == null) {
            results.push(Object.assign({}, fix, { status: 'invalid_value' }));
            continue;
          }
          node.cornerRadius = cornerRadius;
          results.push(Object.assign({}, fix, { status: 'applied' }));

        } else if (fix.property === 'width') {
          const outcome = resizeNode(node, fix.target_value, null);
          results.push(Object.assign({}, fix, { status: outcome.ok ? 'applied' : outcome.status }));

        } else if (fix.property === 'height') {
          const outcome = resizeNode(node, null, fix.target_value);
          results.push(Object.assign({}, fix, { status: outcome.ok ? 'applied' : outcome.status }));

        } else if (fix.property === 'resize') {
          const value = fix.target_value || {};
          const outcome = resizeNode(node, value.width, value.height);
          results.push(Object.assign({}, fix, { status: outcome.ok ? 'applied' : outcome.status }));

        } else if (fix.property === 'itemSpacing' && 'itemSpacing' in node) {
          const spacing = normalizeNumber(fix.target_value);
          if (spacing == null) {
            results.push(Object.assign({}, fix, { status: 'invalid_value' }));
            continue;
          }
          node.itemSpacing = spacing;
          results.push(Object.assign({}, fix, { status: 'applied' }));

        } else if (typeof fix.property === 'string' && fix.property.startsWith('padding.') && 'paddingTop' in node) {
          const side = fix.property.split('.')[1];
          const map  = { top: 'paddingTop', right: 'paddingRight', bottom: 'paddingBottom', left: 'paddingLeft' };
          if (map[side]) {
            const paddingValue = normalizeNumber(fix.target_value);
            if (paddingValue == null) {
              results.push(Object.assign({}, fix, { status: 'invalid_value' }));
              continue;
            }
            node[map[side]] = paddingValue;
            results.push(Object.assign({}, fix, { status: 'applied' }));
          } else {
            results.push(Object.assign({}, fix, { status: 'unsupported_property' }));
          }

        } else if (fix.property === 'layoutMode' && 'layoutMode' in node) {
          if (typeof fix.target_value !== 'string') {
            results.push(Object.assign({}, fix, { status: 'invalid_value' }));
            continue;
          }
          node.layoutMode = fix.target_value;
          results.push(Object.assign({}, fix, { status: 'applied' }));

        } else if (fix.property === 'primaryAxisSizingMode' && 'primaryAxisSizingMode' in node) {
          if (typeof fix.target_value !== 'string') {
            results.push(Object.assign({}, fix, { status: 'invalid_value' }));
            continue;
          }
          node.primaryAxisSizingMode = fix.target_value;
          results.push(Object.assign({}, fix, { status: 'applied' }));

        } else if (fix.property === 'counterAxisSizingMode' && 'counterAxisSizingMode' in node) {
          if (typeof fix.target_value !== 'string') {
            results.push(Object.assign({}, fix, { status: 'invalid_value' }));
            continue;
          }
          node.counterAxisSizingMode = fix.target_value;
          results.push(Object.assign({}, fix, { status: 'applied' }));

        } else {
          results.push(Object.assign({}, fix, { status: 'unsupported_property' }));
        }

      } catch (err) {
        results.push(Object.assign({}, fix, { status: 'error', error: err.message }));
      }
    }

    figma.ui.postMessage({ type: 'fixes-applied', results });
  }

  // Fetch available libraries (triggered by refresh button in UI).
  if (msg.type === 'get-available-libraries') {
    try {
      figma.ui.postMessage({
        type: 'available-libraries',
        libraries: await getAvailableLibraries(),
      });
    } catch (err) {
      figma.ui.postMessage({ type: 'available-libraries', libraries: [], error: err.message });
    }
  }

  if (msg.type === 'close') {
    figma.closePlugin();
  }
};

// ─── Library discovery ────────────────────────────────────────────────────────
// Returns a combined list of available design system libraries for the dropdown.
//
// Strategy:
//   1. Published variable collections  → preferred, gives us token names.
//   2. Component-only libraries        → detected by scanning INSTANCE nodes on
//      the current page and grouping remote components by key prefix (components
//      from the same library share a common 8-char key prefix).
//
// Why the two-pass approach?
//   getAvailableLibraryVariableCollectionsAsync() only returns libraries that
//   have *published variable collections*. Popular libraries like Material 3
//   Design Kit and iOS UI Kit ship components only — they have no published
//   variable collections — so they never appear in that API call. The instance
//   scan catches them.

// Returns published variable collections from enabled libraries.
// Note: Figma Plugin API has no endpoint for listing enabled *component* libraries
// (only variable collections can be enumerated). If the design system is a
// component-only library (e.g. Material 3, iOS UI Kit), the user enters the name
// manually and the downstream agent uses its own knowledge of that system.
async function getAvailableLibraries() {
  const libraries = [];
  try {
    const cols = await figma.teamLibrary.getAvailableLibraryVariableCollectionsAsync();
    for (var i = 0; i < cols.length; i++) {
      var c = cols[i];
      libraries.push({
        key:         c.key,
        name:        c.name,        // e.g. "M3/Baseline"
        libraryName: c.libraryName, // e.g. "Material 3 Design Kit"
        type:        'variables',
      });
    }
  } catch (_) {}
  return libraries;
}

// ─── Figma node serializer ─────────────────────────────────────────────────
// Recursively serialize a node to a plain JSON-safe object.
// boundVariables are included on fills/strokes so the agent can detect
// which colors are already bound to a design system token.

function safe(val) {
  return (typeof val === 'symbol') ? 'mixed' : val;
}

function serializePaint(paint) {
  // Serialize a fill/stroke paint, preserving boundVariables.
  const out = {
    type:      paint.type,
    visible:   paint.visible,
    opacity:   paint.opacity,
    blendMode: paint.blendMode,
  };
  if (paint.color)          out.color          = paint.color;
  if (paint.boundVariables) out.boundVariables  = paint.boundVariables;
  return out;
}

function serializeNode(node) {
  const out = {
    id:   node.id,
    name: node.name,
    type: node.type,
  };

  if ('x' in node)       out.x       = Math.round(node.x);
  if ('y' in node)       out.y       = Math.round(node.y);
  if ('width' in node)   out.width   = Math.round(node.width);
  if ('height' in node)  out.height  = Math.round(node.height);
  if ('visible' in node) out.visible = node.visible;
  if ('opacity' in node) out.opacity = safe(node.opacity);

  // Use serializePaint so boundVariables are preserved per fill/stroke.
  if ('fills' in node && Array.isArray(node.fills)) {
    out.fills = node.fills.map(serializePaint);
  } else if ('fills' in node) {
    out.fills = safe(node.fills);
  }

  if ('strokes' in node && Array.isArray(node.strokes)) {
    out.strokes = node.strokes.map(serializePaint);
  } else if ('strokes' in node) {
    out.strokes = safe(node.strokes);
  }

  if ('effects' in node)      out.effects      = safe(node.effects);
  if ('cornerRadius' in node) out.cornerRadius = safe(node.cornerRadius);

  if ('layoutMode' in node) {
    out.layoutMode            = node.layoutMode;
    out.primaryAxisSizingMode = node.primaryAxisSizingMode;
    out.counterAxisSizingMode = node.counterAxisSizingMode;
    out.itemSpacing           = safe(node.itemSpacing);
    out.padding = {
      top:    safe(node.paddingTop),
      right:  safe(node.paddingRight),
      bottom: safe(node.paddingBottom),
      left:   safe(node.paddingLeft),
    };
  }

  if (node.type === 'TEXT') {
    out.characters          = node.characters;
    out.fontSize            = safe(node.fontSize);
    out.fontName            = safe(node.fontName);
    out.textAlignHorizontal = safe(node.textAlignHorizontal);
    out.textAlignVertical   = safe(node.textAlignVertical);
  }

  // Capture the main component name if this node is a component instance.
  // This tells the agent which library component (if any) this node derives from.
  if (node.type === 'INSTANCE' && node.mainComponent) {
    out.mainComponentName = node.mainComponent.name;
    out.mainComponentKey  = node.mainComponent.key || null;
  }

  // Capture prototype interactions (reactions).
  // A node with an ON_CLICK → NAVIGATE reaction is almost certainly
  // an interactive element (button, tab, link), regardless of its visual shape.
  if ('reactions' in node && Array.isArray(node.reactions) && node.reactions.length > 0) {
    out.reactions = node.reactions.map(function(r) {
      return {
        trigger: r.trigger ? r.trigger.type : null,
        action:  r.action  ? r.action.type  : null,
      };
    });
  }

  // ── Structural summary for component inference ──────────────────────────
  // Give the agent a quick structural fingerprint without requiring full
  // recursive traversal. These hints help the component_auditor apply its
  // semantic inference rules without reading every leaf node.
  if ('children' in node && node.children.length > 0) {
    var childTypes  = {};
    var hasText     = false;
    var hasIcon     = false;  // VECTOR, BOOLEAN_OPERATION used as icons
    var hasImage    = false;  // RECTANGLE with image fill, or image node
    var textContent = [];

    function scanChildren(children) {
      for (var i = 0; i < children.length; i++) {
        var c = children[i];
        var t = c.type || '';
        childTypes[t] = (childTypes[t] || 0) + 1;
        if (t === 'TEXT') {
          hasText = true;
          if (c.characters) textContent.push(c.characters);
        }
        if (t === 'VECTOR' || t === 'BOOLEAN_OPERATION' || t === 'STAR' || t === 'POLYGON') {
          hasIcon = true;
        }
        if (c.fills && c.fills.some && c.fills.some(function(f) { return f.type === 'IMAGE'; })) {
          hasImage = true;
        }
        if ('children' in c && c.children) {
          scanChildren(c.children);
        }
      }
    }
    scanChildren(node.children);

    out.structural_summary = {
      child_count:      node.children.length,
      child_types:      childTypes,
      has_text_child:   hasText,
      has_icon_child:   hasIcon,
      has_image_child:  hasImage,
      text_content:     textContent.slice(0, 5),  // first 5 text strings for context
    };
  }

  if ('children' in node) {
    out.children = node.children.map(serializeNode);
  }

  return out;
}
