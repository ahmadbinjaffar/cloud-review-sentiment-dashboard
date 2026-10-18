"""Clean the raw TripAdvisor dataset into data/reviews.csv.

Raw: data/raw/tripadvisor_reviews_updated.csv (MIT, see data/DATASET_SOURCE.md).
Steps: parse dates -> ISO, keep rating 1-5, drop empty/short text, dedupe
(text+date), add review_id/business_type/source, sort by date.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.models import normalize_date

RAW = ROOT / "data" / "raw" / "tripadvisor_reviews_updated.csv"
OUT = ROOT / "data" / "reviews.csv"
SOURCE = "tripadvisor (github.com/azratuni/Restaurant-Review-Scraping-and-Sentiment-Analysis, MIT)"


def main() -> None:
    df = pd.read_csv(RAW)
    print(f"Raw rows: {len(df)}")

    df = df.rename(columns={"Review Date": "date", "Review Text": "text", "Rating": "rating"})
    df["text"] = df["text"].astype(str).str.strip()
    before = len(df)
    df = df[df["text"].str.len() >= 15]
    print(f"Dropped empty/short text: {before - len(df)}")

    parsed_dates, bad_dates = [], 0
    for value in df["date"]:
        try:
            parsed_dates.append(normalize_date(value))
        except (ValueError, TypeError):
            bad_dates += 1
            parsed_dates.append(None)
    df["date"] = parsed_dates
    df = df.dropna(subset=["date"])
    print(f"Dropped unparseable dates: {bad_dates}")

    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
    before = len(df)
    df = df[df["rating"].between(1, 5)]
    df["rating"] = df["rating"].astype(int)
    print(f"Dropped invalid ratings: {before - len(df)}")

    before = len(df)
    df = df.drop_duplicates(subset=["date", "text"])
    print(f"Dropped duplicate (date,text) rows: {before - len(df)}")

    df = df.sort_values(["date", "text"]).reset_index(drop=True)
    df["review_id"] = ["ta-" + format(i + 1, "04d") for i in range(len(df))]
    df["business_type"] = "restaurant"
    df["business_name"] = None
    df["source"] = SOURCE

    out = df[["review_id", "date", "rating", "text", "business_type", "business_name", "source"]]
    out.to_csv(OUT, index=False)
    print(f"\nWrote {len(out)} reviews -> {OUT}")
    print(f"Date range: {out['date'].min()} .. {out['date'].max()}")
    print(f"Rating distribution:\n{out['rating'].value_counts().sort_index().to_string()}")


if __name__ == "__main__":
    main()
