// code.js runs inside the Figma sandbox — no network access here.
// All GitLab API calls happen in ui.html (the iframe), which can use fetch().
// This file handles: showing the UI, reading Figma data, persisting settings,
// and applying fixes received from the Fix Agent via ui.html.

figma.showUI(__html__, { width: 440, height: 500 });

// On startup, load saved settings from Figma's local storage and send to UI.
async function init() {
  const [
    projectPath,
    baseBranch,
    designSystemUrl,
    token,
    lastReviewBranch,
    lastMrIid,
  ] = await Promise.all([
    figma.clientStorage.getAsync('projectPath'),
    figma.clientStorage.getAsync('baseBranch'),
    figma.clientStorage.getAsync('designSystemUrl'),
    figma.clientStorage.getAsync('token'),
    figma.clientStorage.getAsync('lastReviewBranch'),
    figma.clientStorage.getAsync('lastMrIid'),
  ]);

  figma.ui.postMessage({
    type: 'init',
    settings: {
      projectPath:      projectPath      || '',
      baseBranch:       baseBranch       || 'main',
      designSystemUrl:  designSystemUrl  || '',
      token:            token            || '',
      lastReviewBranch: lastReviewBranch || '',
      lastMrIid:        lastMrIid        || '',
    },
  });
}

init();

// ─── hex ↔ Figma RGBA helpers ──────────────────────────────────────────────

function hexToFigmaRgb(hex) {
  // Accepts "#RRGGBB" or "#RGB", returns { r, g, b } in 0–1 range.
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

  // Persist settings; token only if user opts in.
  if (msg.type === 'save-settings') {
    const s = msg.settings;
    await figma.clientStorage.setAsync('projectPath',     s.projectPath);
    await figma.clientStorage.setAsync('baseBranch',      s.baseBranch);
    await figma.clientStorage.setAsync('designSystemUrl', s.designSystemUrl);
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
  if (msg.type === 'get-figma-export') {
    try {
      const page      = figma.currentPage;
      const selection = figma.currentPage.selection;
      const targets   = selection.length > 0 ? [...selection] : [page];

      const payload = {
        exportedAt:      new Date().toISOString(),
        designSystemUrl: msg.designSystemUrl || '',
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
  // msg.fixes: Array<{ node_id, node_name, property, fill_index, target_value, review_type }>
  if (msg.type === 'apply-fixes') {
    const results = [];

    for (const fix of msg.fixes) {
      const node = figma.getNodeById(fix.node_id);

      if (!node) {
        results.push({ ...fix, status: 'not_found' });
        continue;
      }

      try {
        if ((fix.property === 'fills' || fix.property === 'strokes') && fix.property in node) {
          const prop  = fix.property;
          const fills = JSON.parse(JSON.stringify(node[prop])); // deep clone

          const idx = typeof fix.fill_index === 'number' ? fix.fill_index : 0;
          if (!fills[idx]) {
            results.push({ ...fix, status: 'fill_index_missing' });
            continue;
          }

          fills[idx] = { ...fills[idx], color: hexToFigmaRgb(fix.target_value) };
          node[prop] = fills;
          results.push({ ...fix, status: 'applied' });

        } else if (fix.property === 'fontSize' && 'fontSize' in node) {
          node.fontSize = fix.target_value;
          results.push({ ...fix, status: 'applied' });

        } else if (fix.property === 'itemSpacing' && 'itemSpacing' in node) {
          node.itemSpacing = fix.target_value;
          results.push({ ...fix, status: 'applied' });

        } else if (fix.property.startsWith('padding.') && 'paddingTop' in node) {
          const side = fix.property.split('.')[1]; // top | right | bottom | left
          const map  = { top: 'paddingTop', right: 'paddingRight', bottom: 'paddingBottom', left: 'paddingLeft' };
          if (map[side]) {
            node[map[side]] = fix.target_value;
            results.push({ ...fix, status: 'applied' });
          } else {
            results.push({ ...fix, status: 'unsupported_property' });
          }

        } else {
          results.push({ ...fix, status: 'unsupported_property' });
        }

      } catch (err) {
        results.push({ ...fix, status: 'error', error: err.message });
      }
    }

    figma.ui.postMessage({ type: 'fixes-applied', results });
  }

  if (msg.type === 'close') {
    figma.closePlugin();
  }
};

// ─── Figma node serializer ─────────────────────────────────────────────────
// Recursively serialize a node to a plain JSON-safe object.
// Symbols (figma.mixed) are replaced with the string "mixed".

function safe(val) {
  return (typeof val === 'symbol') ? 'mixed' : val;
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

  if ('fills' in node)        out.fills        = safe(node.fills);
  if ('strokes' in node)      out.strokes      = safe(node.strokes);
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

  if ('children' in node) {
    out.children = node.children.map(serializeNode);
  }

  return out;
}
