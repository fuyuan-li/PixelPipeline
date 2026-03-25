# Figma Plugin Installation Guide

This folder contains a local Figma plugin named `Figma -> GitLab MR`.

The plugin lets a designer:

- export the current Figma selection into a GitLab merge request for review,
- run a design-system audit through the GitLab flow,
- load the generated fix spec,
- apply suggested fixes back in Figma.

## What Is Included

Below files are packaged into a single `.zip` to download:

- `manifest.json`
- `code.js`
- `ui.html`
- `README.md`

Users should unzip the archive locally before importing the plugin into Figma.

## Install In Figma

1. Download the plugin `.zip`.
2. Unzip it to a local folder.
3. Open the Figma desktop app.
4. Open a design file.
5. Go to `Plugins` -> `Development` -> `Import plugin from manifest...`
6. Choose the `manifest.json` file from the unzipped folder.
7. Figma will add the plugin to your local development plugins.

After that, you can run it from `Plugins` -> `Development` -> `Figma -> GitLab MR`.

## Before First Use

Prepare the following:

- A GitLab personal access token with `api` scope
- The target GitLab project path, for example `group/project`
- The base branch you want to review against, for example `main`
- An optional save folder inside the repository, for example `demo` or `reviews/mobile`

## Create A Review MR

1. In Figma, select the frame or page you want to review.
2. Run `Figma -> GitLab MR`.
3. In the `Submit Review` tab, fill in:
   - `Project Path`
   - `Base Branch`
   - `Save Folder` (optional; leave blank to use the project root)
   - `Design System`
   - `GitLab Personal Access Token`
4. Click `Create MR & Start Review`.
5. Wait for the plugin to create the review branch and merge request.

## Apply Suggested Fixes

1. Open the plugin again.
2. Switch to the `Apply Fixes` tab.
3. Enter or confirm the review branch name.
4. If needed, switch back to `Submit Review` and confirm the same `Save Folder` used when the MR was created.
5. Click `Load Fixes`.
6. Review the suggested fixes.
7. Click `Apply Selected Fixes`.

## Notes

- The plugin is imported locally through Figma's development plugin flow. It is not installed from the Figma Community.
- If `Remember token` is enabled, the GitLab token is stored in Figma's local storage on that machine.
- `Save Folder` defaults to `demo`. If the folder does not exist yet, GitLab will create the path as part of the committed file paths.
- Leaving `Save Folder` blank saves generated files in the repository root.
- Generated files are written directly into the chosen save folder:
  - `figma-export-<timestamp>.json`
  - `ds-catalog.json`
  - `component-migration-plan.json`
  - `component-patch-plan.json`
  - `figma-fix-spec.json`
- The plugin currently targets `gitlab.com` and the demo review flow configured in this repository.
