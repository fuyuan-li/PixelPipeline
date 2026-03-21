// code.js runs inside the Figma sandbox — no network access here.
// All GitLab API calls happen in ui.html (the iframe), which can use fetch().
// This file handles: showing the UI, reading Figma data, and persisting settings
// to Figma's local clientStorage (never to the source code).

figma.showUI(__html__, { width: 440, height: 430 });

// On startup, load saved settings from Figma's local storage and send to UI.
// gitlabBaseUrl and flowAccount are hardcoded constants — not stored here.
// The token is optionally saved if the user checks "Remember token".
async function init() {
  const [
    projectPath,
    baseBranch,
    designSystemUrl,
    token,
  ] = await Promise.all([
    figma.clientStorage.getAsync('projectPath'),
    figma.clientStorage.getAsync('baseBranch'),
    figma.clientStorage.getAsync('designSystemUrl'),
    figma.clientStorage.getAsync('token'),
  ]);

  figma.ui.postMessage({
    type: 'init',
    settings: {
      projectPath:     projectPath     || '',
      baseBranch:      baseBranch      || 'main',
      designSystemUrl: designSystemUrl || '',
      token:           token           || '',
    },
  });
}

init();

figma.ui.onmessage = async (msg) => {

  // Persist non-sensitive settings; token only saved if user opts in.
  if (msg.type === 'save-settings') {
    const s = msg.settings;
    await figma.clientStorage.setAsync('projectPath',      s.projectPath);
    await figma.clientStorage.setAsync('baseBranch',       s.baseBranch);
    await figma.clientStorage.setAsync('designSystemUrl',  s.designSystemUrl);

    if (s.rememberToken && s.token) {
      await figma.clientStorage.setAsync('token', s.token);
    } else {
      await figma.clientStorage.deleteAsync('token');
    }
  }

  // Export the current selection (or whole page if nothing selected) as JSON
  // and send it back to ui.html so it can be committed to GitLab.
  if (msg.type === 'get-figma-export') {
    try {
      const page = figma.currentPage;
      const selection = figma.currentPage.selection;
      const targets = selection.length > 0 ? [...selection] : [page];

      const payload = {
        exportedAt: new Date().toISOString(),
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

  if (msg.type === 'close') {
    figma.closePlugin();
  }
};

// Recursively serialize a Figma node to a plain JSON-safe object.
// We capture layout, visual, and text properties that are useful for review.
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
  if ('opacity' in node) out.opacity = node.opacity;

  if ('fills' in node)         out.fills         = node.fills;
  if ('strokes' in node)       out.strokes       = node.strokes;
  if ('effects' in node)       out.effects       = node.effects;
  if ('cornerRadius' in node)  out.cornerRadius  = node.cornerRadius;

  if ('layoutMode' in node) {
    out.layoutMode             = node.layoutMode;
    out.primaryAxisSizingMode  = node.primaryAxisSizingMode;
    out.counterAxisSizingMode  = node.counterAxisSizingMode;
    out.itemSpacing            = node.itemSpacing;
    out.padding = {
      top:    node.paddingTop,
      right:  node.paddingRight,
      bottom: node.paddingBottom,
      left:   node.paddingLeft,
    };
  }

  if (node.type === 'TEXT') {
    out.characters          = node.characters;
    out.fontSize            = node.fontSize;
    out.fontName            = node.fontName;
    out.textAlignHorizontal = node.textAlignHorizontal;
    out.textAlignVertical   = node.textAlignVertical;
  }

  if ('children' in node) {
    out.children = node.children.map(serializeNode);
  }

  return out;
}
