# Dataset Source

## What is committed to GitHub

| File | Status |
|---|---|
| `data/reviews.csv` | Full cleaned dataset (1,214 rows) — **local only, not committed** |
| `data/sample_reviews.csv` | **Committed**: 20-row rating-stratified sample (1×1★, 1×2★, 2×3★, 4×4★, 12×5★) so the project runs out of the box |
| `data/raw/` | Raw download — local only, git-ignored |

`scripts/seed_db.py` seeds from `data/reviews.csv` when present and falls back
to `data/sample_reviews.csv` automatically. Rebuild the sample any time with
`python scripts/make_sample_dataset.py` (deterministic, even spacing per rating).

## `data/reviews.csv` — cleaned analysis dataset (local)

| Field | Value |
|---|---|
| Origin | TripAdvisor restaurant reviews, scraped and published by **Azra Tuni (2024)** |
| Repository | https://github.com/azratuni/Restaurant-Review-Scraping-and-Sentiment-Analysis |
| File used | `tripadvisor_reviews_updated.csv` (raw copy kept locally in `data/raw/`, git-ignored) |
| Licence | **MIT** (repository `LICENSE`, Copyright (c) 2024 Azra Tuni) |
| Downloaded | 2026-10-15 |
| Rows raw → cleaned | 1216 → **1214** |
| Columns | `review_id, date, rating, text, business_type, business_name, source` |
| Date range | 2012-07-21 … 2024-03-04 |
| Rating spread | 1★:5, 2★:7, 3★:12, 4★:80, 5★:1110 (skew is inherent to TripAdvisor data) |
| Vertical | restaurants (a small-business category; salon/shop data not available in one MIT dataset with date+rating+text) |

**This is REAL public data, not synthetic.** The vertical is restaurants only;
the pipeline is vertical-agnostic (`business_type` column ready for salons/shops).

## Cleaning steps (reproducible via `scripts/prepare_dataset.py`)

1. Rename columns (`Review Date/Review Text/Rating` → `date/text/rating`).
2. Drop rows with text shorter than 15 characters — 0 rows removed.
3. Parse dates to ISO `YYYY-MM-DD` (multi-format parser in `src/models.py`) — 0 unparseable.
4. Keep ratings within 1–5 — 0 removed.
5. Drop duplicate `(date, text)` pairs — 2 removed.
6. Sort by date; assign stable `review_id` (`ta-0001`…); tag `business_type=restaurant`
   and `source=tripadvisor (…, MIT)`.

## Synthetic data

None. A real MIT-licensed dataset was downloadable, so no synthetic reviews were
generated (see task rule: prefer real data when available).
