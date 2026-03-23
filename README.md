# Figma Design System Migration Pipeline

This project is a Figma-to-GitLab review and migration pipeline for design system adoption.

Designers can:
- sketch a new interface in Figma, or
- take an existing design that needs to be migrated to a different design system.

Using the local Figma plugin, the designer selects the target design system and submits the design into a GitLab merge request. A custom GitLab Flow then reads cached design system data from GCP, chooses suitable target components based on the design intent, and sends back a fix spec that the Figma plugin can apply in one click.

## Current Product Direction

The latest workflow is:

1. A designer selects frames or a page in Figma.
2. The plugin asks which target design system to migrate to.
3. The plugin exports the Figma structure as JSON and opens a GitLab merge request.
4. A custom GitLab Flow reads the export and loads cached target design system data from GCP.
5. The flow identifies the best matching components or tokens for the intended UI.
6. The flow writes review results and a fix spec back to the merge request branch.
7. The Figma plugin fetches the fix spec and applies the migration in one click.

## Why GCP Exists In This Architecture

GCP is used as a fast cache layer for scraped design system data.

Instead of scraping component and token definitions during every review, we:
- scrape supported design systems ahead of time,
- normalize the results into a shared schema,
- store them in isolated GCP storage objects,
- expose them through a lightweight Cloud Function for fast lookup.

This keeps the GitLab Flow fast, deterministic, and cheap during the demo.

## High-Level Architecture

```text
Figma Designer
  -> Figma plugin
  -> GitLab merge request
  -> GitLab custom Flow
  -> GCP cached design system data
  -> migration review + fix spec
  -> Figma plugin Apply Fixes
```

## Repository Areas

- `local/figma-ci-plugin/`: Figma plugin that exports design data and applies fixes
- `flows/figma-review.yml`: GitLab custom Flow for intake, design-system lookup, audit, and review writing
- `tools/scraper/`: scrapers that collect supported design system data and upload it to GCP
- `gcloud/functions/design-tokens-api/`: Cloud Function that serves cached design system data to the flow
- `TODO.md`: current implementation notes, architecture details, and remaining setup work

## Current Status

The local codebase already includes:
- the Figma plugin export/apply flow,
- the GitLab review flow,
- the scraper for supported design systems,
- the Cloud Function code for serving cached token data.

The main remaining work is infrastructure setup and end-to-end verification:
- create the GCP project resources,
- create the storage bucket,
- run the scraper for real,
- deploy the Cloud Function,
- connect the deployed URL into the GitLab Flow,
- test the full pipeline end to end.
