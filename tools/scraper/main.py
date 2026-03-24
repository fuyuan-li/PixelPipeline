"""
Design System Token Scraper
===========================
Fetches tokens from Material Design 3, Ant Design, and Carbon Design System,
normalises them to a common schema, and uploads to Google Cloud Storage.

Configuration (in order of priority — higher overrides lower):
  1. CLI flags        --systems md3 --bucket my-bucket --dry-run
  2. scraper.config.yml  (sits next to this file)
  3. Built-in defaults

Usage:
    # Use scraper.config.yml (recommended)
    python main.py

    # Override: only MD3, dry run
    python main.py --systems md3 --dry-run

    # Override: all systems, upload to a different bucket
    python main.py --systems md3 antd carbon --bucket my-other-bucket
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from scrapers import md3, carbon, atlassian

SCRAPERS = {
    "md3":       md3.scrape,
    "carbon":    carbon.scrape,
    "atlassian": atlassian.scrape,
}

CONFIG_FILE = Path(__file__).parent / "scraper.config.yml"

# ── Config loader ─────────────────────────────────────────────────────────────

def load_config():
    """Load scraper.config.yml. Returns a dict with defaults if file is missing."""
    defaults = {
        "systems": list(SCRAPERS.keys()),
        "bucket":  "figma-design-tokens",
        "dry_run": False,
    }
    if not CONFIG_FILE.exists():
        return defaults

    try:
        import yaml  # optional — only needed if config file exists
        with open(CONFIG_FILE) as f:
            data = yaml.safe_load(f) or {}
        return {**defaults, **{k: v for k, v in data.items() if v is not None}}
    except ImportError:
        # PyYAML not installed — fall back to a simple line parser
        data = {}
        with open(CONFIG_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or not line:
                    continue
                if line.startswith("- "):
                    # list item under 'systems'
                    data.setdefault("systems", []).append(line[2:].strip())
                elif ":" in line:
                    key, _, val = line.partition(":")
                    val = val.strip()
                    if val.lower() == "true":
                        data[key.strip()] = True
                    elif val.lower() == "false":
                        data[key.strip()] = False
                    elif val:
                        data[key.strip()] = val
        return {**defaults, **data}


# ── Main ──────────────────────────────────────────────────────────────────────

def run(bucket_name: str, systems: list, dry_run: bool):
    print(f"  bucket  : {bucket_name}")
    print(f"  systems : {systems}")
    print(f"  dry_run : {dry_run}")
    print()

    results = {}
    for slug in systems:
        if slug not in SCRAPERS:
            print(f"[SKIP] Unknown system: {slug}")
            continue

        print(f"[{slug.upper()}] Scraping...", end=" ", flush=True)
        try:
            data = SCRAPERS[slug]()
            data["scraped_at"] = datetime.now(timezone.utc).isoformat()
            count = len(data.get("tokens", []))
            source = "(fallback)" if "fallback" in data.get("source", "") and count > 0 else "(GitHub)"
            print(f"✓  {count} tokens {source}")
            results[slug] = data
        except Exception as e:
            print(f"✗  ERROR: {e}")

    if not results:
        print("No data scraped. Exiting.")
        sys.exit(1)

    if dry_run:
        _write_local(results)
    else:
        _upload_to_gcs(results, bucket_name)


def _write_local(results: dict):
    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    for slug, data in results.items():
        path = out_dir / f"{slug}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[DRY RUN] Written → {path}")


def _upload_to_gcs(results: dict, bucket_name: str):
    try:
        from google.cloud import storage
    except ImportError:
        print("google-cloud-storage not installed. Run: pip install -r requirements.txt")
        sys.exit(1)

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    for slug, data in results.items():
        blob = bucket.blob(f"{slug}.json")
        blob.upload_from_string(
            json.dumps(data, indent=2, ensure_ascii=False),
            content_type="application/json",
        )
        print(f"[GCS] Uploaded → gs://{bucket_name}/{slug}.json")


if __name__ == "__main__":
    cfg = load_config()

    parser = argparse.ArgumentParser(description="Scrape design system tokens.")
    parser.add_argument("--bucket",   default=None,
                        help=f"GCS bucket name (config default: {cfg['bucket']})")
    parser.add_argument("--systems",  nargs="+", default=None,
                        choices=list(SCRAPERS.keys()),
                        help=f"Systems to scrape (config default: {cfg['systems']})")
    parser.add_argument("--dry-run",  action="store_true", default=None,
                        help="Write JSON locally instead of uploading to GCS")
    args = parser.parse_args()

    # CLI overrides config
    bucket  = args.bucket   or cfg["bucket"]
    systems = args.systems  or cfg["systems"]
    dry_run = args.dry_run  if args.dry_run else cfg["dry_run"]

    run(bucket_name=bucket, systems=systems, dry_run=dry_run)
