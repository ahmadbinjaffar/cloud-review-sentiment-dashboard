"""Build data/sample_reviews.csv (20 rows) from data/reviews.csv.

The full dataset is not committed to GitHub (see data/DATASET_SOURCE.md);
the committed 20-row sample keeps the project runnable out of the box
(pipeline, dashboard, seed_db.py falls back to it automatically).

Rating-stratified pick (1x1, 1x2, 2x3, 4x4, 12x5 = 20 rows), evenly spaced
within each rating group so the sample is deterministic.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FULL = ROOT / "data" / "reviews.csv"
SAMPLE = ROOT / "data" / "sample_reviews.csv"
STRATA = {1: 1, 2: 1, 3: 2, 4: 4, 5: 12}


def main() -> None:
    if not FULL.is_file():
        raise SystemExit("data/reviews.csv not found - see data/DATASET_SOURCE.md")
    df = pd.read_csv(FULL)

    picks = []
    for rating, want in STRATA.items():
        group = df[df["rating"] == rating].sort_values("review_id")
        if len(group) < want:
            raise SystemExit(f"rating {rating}: need {want} rows, have {len(group)}")
        idx = [round(i * (len(group) - 1) / (want - 1)) for i in range(want)] if want > 1 else [0]
        picks.append(group.iloc[sorted(set(idx))])

    sample = pd.concat(picks).sort_values("review_id")
    sample.to_csv(SAMPLE, index=False)
    print(f"Wrote {len(sample)} rows -> {SAMPLE}")
    print(sample["rating"].value_counts().sort_index().to_string())


if __name__ == "__main__":
    main()
