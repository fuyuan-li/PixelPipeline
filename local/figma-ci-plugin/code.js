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
        if (lib.key) {
          // Variable collection — we can fetch token names.
          try {
            const libVars = await figma.teamLibrary.getVariablesInLibraryCollectionAsync(lib.key);
            designSystem = {
              name:           lib.libraryName,
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
      const node = figma.getNodeById(fix.node_id);

      if (!node) {
        results.push(Object.assign({}, fix, { status: 'not_found' }));
        continue;
      }

      try {
        if ((fix.property === 'fills' || fix.property === 'strokes') && fix.property in node) {
          const prop  = fix.property;
          const fills = JSON.parse(JSON.stringify(node[prop]));
          const idx   = typeof fix.fill_index === 'number' ? fix.fill_index : 0;

          if (!fills[idx]) {
            results.push(Object.assign({}, fix, { status: 'fill_index_missing' }));
            continue;
          }

          fills[idx] = Object.assign({}, fills[idx], { color: hexToFigmaRgb(fix.target_value) });
          node[prop] = fills;
          results.push(Object.assign({}, fix, { status: 'applied' }));

        } else if (fix.property === 'fontSize' && 'fontSize' in node) {
          node.fontSize = fix.target_value;
          results.push(Object.assign({}, fix, { status: 'applied' }));

        } else if (fix.property === 'itemSpacing' && 'itemSpacing' in node) {
          node.itemSpacing = fix.target_value;
          results.push(Object.assign({}, fix, { status: 'applied' }));

        } else if (fix.property.startsWith('padding.') && 'paddingTop' in node) {
          const side = fix.property.split('.')[1];
          const map  = { top: 'paddingTop', right: 'paddingRight', bottom: 'paddingBottom', left: 'paddingLeft' };
          if (map[side]) {
            node[map[side]] = fix.target_value;
            results.push(Object.assign({}, fix, { status: 'applied' }));
          } else {
            results.push(Object.assign({}, fix, { status: 'unsupported_property' }));
          }

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

  if ('children' in node) {
    out.children = node.children.map(serializeNode);
  }

  return out;
}
