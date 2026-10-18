"""Load the review dataset into the configured storage backend.

Uses data/reviews.csv (full dataset, not committed) or falls back to the
committed data/sample_reviews.csv (20 rows) so a fresh clone runs out of the box.
See data/DATASET_SOURCE.md for how to rebuild the full dataset.

Usage:
  python scripts/seed_db.py            # ingest CSV into empty/existing DB
  python scripts/seed_db.py --reset    # delete the SQLite DB first
  python scripts/seed_db.py --process  # also run sentiment over all unprocessed rows
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import get_settings
from src.handlers import lambda_handler

FULL_CSV = ROOT / "data" / "reviews.csv"
SAMPLE_CSV = ROOT / "data" / "sample_reviews.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the review database")
    parser.add_argument("--reset", action="store_true", help="delete the SQLite DB before seeding")
    parser.add_argument("--process", action="store_true", help="run sentiment analysis after seeding")
    parser.add_argument("--batch", type=int, default=100, help="processing batch size with --process")
    args = parser.parse_args()

    settings = get_settings()
    if args.reset and settings.storage_backend == "sqlite":
        db = Path(settings.sqlite_path)
        if db.exists():
            db.unlink()
            print(f"Deleted {db}")

    csv_path = FULL_CSV if FULL_CSV.is_file() else SAMPLE_CSV
    if not csv_path.is_file():
        raise SystemExit(
            f"{FULL_CSV} and {SAMPLE_CSV} not found - see data/DATASET_SOURCE.md"
        )
    if csv_path == SAMPLE_CSV:
        print("Full dataset not present - seeding from data/sample_reviews.csv (20 rows)")

    rel_path = csv_path.relative_to(ROOT).as_posix()
    event = {
        "version": "2.0",
        "rawPath": "/ingest",
        "requestContext": {"http": {"method": "POST", "path": "/ingest"}},
        "body": json.dumps({"path": rel_path, "filename": csv_path.name}),
    }
    response = lambda_handler(event, None)
    print(json.dumps(json.loads(response["body"]), indent=2))
    if response["statusCode"] >= 400:
        raise SystemExit("Seeding failed")

    if args.process:
        done = 0
        while True:
            result = lambda_handler(
                {"version": "2.0", "rawPath": "/process",
                 "requestContext": {"http": {"method": "POST", "path": "/process"}},
                 "body": json.dumps({"limit": args.batch})},
                None,
            )
            payload = json.loads(result["body"])
            summary = payload["summary"]
            done += summary["processed"]
            print(f"Processed batch: {summary}")
            if summary["processed"] == 0 or summary["failed"]:
                break
        print(f"Total processed: {done}")


if __name__ == "__main__":
    main()
