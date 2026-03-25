# PROJECT_NAME_PLACEHOLDER

Bring GitLab CI/CD to semantic design review and design system auto-alignment.

This project turns a Figma selection into a GitLab merge request, runs a semantic review against a target design system, generates machine-readable fixes, and applies those fixes back in Figma.

This is not only a design-system migration tool.

Its broader purpose is to bring software-style review pipelines into design engineering:

- submit designs through a GitLab workflow,
- review them with CI/CD-style automation,
- understand what UI elements semantically are,
- align them to a target design system,
- and send actionable fixes back to the designer.

Design-system migration is one strong use case, but not the ceiling of the product.

## Product Positioning

Most design review automation only works when the file is already cleanly structured:

- components are correctly attached,
- variables are already bound,
- layer names are reliable,
- and the design-system mapping is explicit.

This project is built for the messier real world.

It reviews raw drafts, detached instances, and loosely structured frames by inferring intent from the design itself. Instead of checking only `component class` or `token binding`, it asks a higher-level question:

`What is this UI element supposed to be?`

Examples:

- this rectangle plus text plus click behavior is semantically a button,
- this grouped icon plus label plus spacing pattern is a tab item,
- this layout behaves like a card, list row, input field, or navigation bar.

That semantic layer is what makes the system useful for both:

- early draft alignment to a design system,
- and migration of legacy designs to a new design system.

## What The Product Does

At a high level, the product provides:

- semantic design review through GitLab merge requests,
- design-system-aware auditing against a target system,
- automatic generation of migration and patch plans,
- one-click fix application back in Figma,
- and reusable CI/CD infrastructure for design engineering workflows.

## Core Workflow

The current workflow is:

1. A designer selects frames or a page in Figma.
2. The plugin asks which target design system should be used for review.
3. The plugin exports the Figma structure as JSON and opens a GitLab merge request.
4. A GitLab flow loads a cached design-system catalog containing tokens and component definitions.
5. The flow semantically classifies each relevant node in the design.
6. The flow decides how the design should align to the target design system.
7. The flow writes a migration plan, patch plan, and final fix spec back to the branch.
8. The Figma plugin fetches the fix spec and applies the suggested fixes in one click.

## Why The Semantic Layer Matters

The key differentiator is semantic inference.

The system does not rely only on explicit Figma metadata such as:

- component instance identity,
- published variable collections,
- or perfect layer naming.

It also uses signals from the design structure itself, including:

- node hierarchy,
- dimensions,
- spacing,
- text content,
- interaction metadata,
- and overall composition patterns.

That allows review and alignment to work even when the source design is still a draft, partially detached, or not yet modeled as a formal design-system component tree.

## Main Use Cases

This product can support multiple workflows:

- semantic review of new design drafts before handoff,
- automatic alignment of ad hoc designs to a target design system,
- migration from one design system to another,
- review of legacy files that no longer preserve clean component relationships,
- and design governance through GitLab-native workflows.

In other words:

- `design-system migration` is an important use case,
- `semantic design review and auto-alignment` is the broader product category.

## Why GCP Exists In This Architecture

GCP is used as a fast cache layer for scraped design-system data.

Instead of scraping component and token definitions during every review, this project:

- scrapes supported design systems ahead of time,
- normalizes the results into a shared schema,
- stores them in isolated GCP storage objects,
- and exposes them through a lightweight Cloud Function for fast lookup.

This keeps the GitLab flow fast, deterministic, and resource-efficient.

## High-Level Architecture

```text
Figma Designer
  -> Figma plugin
  -> GitLab merge request
  -> GitLab review / CI pipeline
  -> semantic classification + design-system catalog lookup
  -> migration plan + patch plan + fix spec
  -> Figma plugin Apply Fixes
```

## Repository Areas

- `local/figma-ci-plugin/`: Figma plugin that exports design data and applies fixes
- `flows/figma-review.yml`: GitLab flow for intake, catalog verification, semantic classification, patch planning, and review writing
- `tools/scraper/`: scrapers that collect supported design-system data and upload it to GCP
- `gcloud/functions/design-tokens-api/`: Cloud Function that serves cached token and component data to the flow
- `TODO.md`: implementation notes, architecture details, and remaining setup work

## Install The Figma Plugin

For end-user installation steps, see [local/figma-ci-plugin/README.md](local/figma-ci-plugin/README.md).

## Current Status

The local codebase already includes:

- the Figma plugin export/apply flow,
- the GitLab review flow,
- the semantic classification and patch-planning stages,
- the scraper for supported design systems,
- and the Cloud Function code for serving cached design-system data.

The main remaining work is infrastructure setup and end-to-end verification:

- create the GCP project resources,
- create the storage bucket,
- run the scraper for real,
- deploy the Cloud Function,
- connect the deployed URL into the GitLab flow,
- and test the full pipeline end to end.
