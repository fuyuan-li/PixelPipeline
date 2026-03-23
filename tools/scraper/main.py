"""
Design System Token Scraper
===========================
Fetches tokens from Material Design 3, Ant Design, and Carbon Design System,
normalises them to a common schema, and uploads to Google Cloud Storage.

Usage:
    # Upload to GCS (default)
    python main.py --bucket figma-design-tokens

    # Dry run — write JSON files locally instead of uploading
    python main.py --dry-run

    # Only scrape specific systems
    python main.py --bucket figma-design-tokens --systems md3 antd
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from scrapers import md3, antd, carbon

SCRAPERS = {
    "md3":    md3.scrape,
    "antd":   antd.scrape,
    "carbon": carbon.scrape,
}


def run(bucket_name: str, systems: list[str], dry_run: bool):
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
            print(f"✓  {count} tokens")
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
    os.makedirs("output", exist_ok=True)
    for slug, data in results.items():
        path = f"output/{slug}.json"
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
        blob_name = f"{slug}.json"
        blob      = bucket.blob(blob_name)
        blob.upload_from_string(
            json.dumps(data, indent=2, ensure_ascii=False),
            content_type="application/json",
        )
        print(f"[GCS] Uploaded → gs://{bucket_name}/{blob_name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape design system tokens and upload to GCS.")
    parser.add_argument("--bucket",  default="figma-design-tokens",
                        help="GCS bucket name (default: figma-design-tokens)")
    parser.add_argument("--systems", nargs="+", default=list(SCRAPERS.keys()),
                        choices=list(SCRAPERS.keys()),
                        help="Which design systems to scrape (default: all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Write JSON files locally instead of uploading to GCS")
    args = parser.parse_args()

    run(
        bucket_name=args.bucket,
        systems=args.systems,
        dry_run=args.dry_run,
    )
