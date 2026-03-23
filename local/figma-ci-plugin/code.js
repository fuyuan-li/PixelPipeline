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

// ─── Component replacement helper ─────────────────────────────────────────
//
// Strategy for finding the right library component:
//   1. Search all INSTANCE nodes on the current page for a mainComponent whose
//      name contains fix.figma_search_name. If found, import by key and replace.
//   2. If not found on page, try all pages (some teams place a component
//      showcase page where all library components are instanced).
//   3. If still not found, report "component_not_found" with guidance so the
//      designer knows to place one instance of the target component first.
//
// Why this approach?
//   figma.importComponentByKeyAsync(key) requires the Figma component key, which
//   is unique to each published library file. Rather than hardcoding keys (which
//   change when a library is republished), we discover the key at runtime by
//   scanning existing instances. This works as long as the library is enabled
//   and at least one instance of the target component exists somewhere in the file.

async function applyComponentFix(fix, node, results) {
  const searchName = (fix.figma_search_name || fix.inferred_component || '').toLowerCase();

  // ── Step 1: Search all instances on all pages for a matching component key
  let targetKey  = null;
  let targetName = null;

  const pagesToSearch = [figma.currentPage].concat(
    figma.root.children.filter(p => p !== figma.currentPage)
  );

  outer:
  for (var pi = 0; pi < pagesToSearch.length; pi++) {
    var page = pagesToSearch[pi];
    var instances;
    try {
      instances = page.findAllWithCriteria({ types: ['INSTANCE'] });
    } catch (_) {
      instances = page.findAll(function(n) { return n.type === 'INSTANCE'; });
    }
    for (var ii = 0; ii < instances.length; ii++) {
      var inst = instances[ii];
      if (inst.mainComponent) {
        var compName = inst.mainComponent.name.toLowerCase();
        if (compName.indexOf(searchName) !== -1) {
          targetKey  = inst.mainComponent.key;
          targetName = inst.mainComponent.name;
          break outer;
        }
      }
    }
  }

  if (!targetKey) {
    // Couldn't find a matching component instance in the file.
    results.push(Object.assign({}, fix, {
      status:  'component_not_found',
      message: 'No instance of "' + (fix.target_component_name || fix.figma_search_name) + '" found in this file. ' +
               'To apply this fix: (1) enable the ' + (fix.target_component_name || 'design system') + ' library, ' +
               '(2) place one instance of the "' + (fix.figma_search_name || fix.inferred_component) + '" component anywhere on the canvas, ' +
               'then click Apply Fixes again.',
    }));
    return;
  }

  // ── Step 2: Import the component and create an instance
  var comp     = await figma.importComponentByKeyAsync(targetKey);
  var instance = comp.createInstance();

  // Position at the same location as the original node
  instance.x = node.x;
  instance.y = node.y;

  // Try to preserve width; height is driven by the component spec so we only
  // override it if the component explicitly supports resizing.
  try {
    instance.resize(
      fix.node_width  || node.width  || instance.width,
      fix.node_height || node.height || instance.height
    );
  } catch (_) {
    // Some components don't allow arbitrary resize — that's fine.
  }

  // ── Step 3: Replace the original node
  var parent = node.parent;
  if (parent) {
    var idx = parent.children.indexOf(node);
    if (idx !== -1) {
      parent.insertChild(idx, instance);
    } else {
      parent.appendChild(instance);
    }
    node.remove();
    results.push(Object.assign({}, fix, {
      status:           'applied',
      applied_component: targetName,
    }));
  } else {
    // Node has no parent (unusual); append to current page instead.
    figma.currentPage.appendChild(instance);
    node.remove();
    results.push(Object.assign({}, fix, {
      status:           'applied',
      applied_component: targetName,
      note:             'Node had no parent; instance appended to current page.',
    }));
  }
}

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
        // slug comes pre-resolved from ui.html's DESIGN_SYSTEM_SLUG_MAP.
        // Pass it through so the Flow can call the design-tokens API directly
        // without guessing, while still having the human-readable name for review text.
        const slug = lib.slug ?? null;
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

      // ── Component replacement fix ────────────────────────────────────────
      // This is handled separately because it may need to remove the original
      // node and insert a new instance; we don't need to look up the node first
      // (the node may not exist yet if we're doing a dry-run preview).
      if (fix.property === 'component' || fix.fix_type === 'component') {
        const node = figma.getNodeById(fix.node_id);
        if (!node) {
          results.push(Object.assign({}, fix, { status: 'not_found' }));
          continue;
        }
        try {
          await applyComponentFix(fix, node, results);
        } catch (err) {
          results.push(Object.assign({}, fix, { status: 'error', error: err.message }));
        }
        continue;
      }

      // ── Property-level fixes (color, font, layout) ───────────────────────
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
