# TEST_REPORT — Cloud-Based Customer Review Sentiment Analysis Dashboard

| Field | Value |
|---|---|
| Date executed | **2026-10-15** |
| Environment | Windows 11, Python **3.13.7** (`.venv`), pytest **8.4.2** |
| Command | `& '.venv\Scripts\python.exe' -m pytest` (from `Cloud_Project/`, `pytest.ini` sets `testpaths = tests`) |
| Result | **105 passed, 0 failed, 0 skipped, 13.89 s** |
| Lint | `ruff check tests src scripts experiments` → clean (0 errors) |

Verbatim final summary line:

```
105 passed in 13.89s
```

## 1. What was tested (per file)

| File | Tests | Scope |
|---|---:|---|
| `tests/test_sentiment.py` | 14 | Engine factory (default/unknown/unavailable), 3-class rule incl. exact-threshold boundary, VADER + TextBlob positive/negative/neutral labels, confidence & score ranges, neutral-band widening via `neutral_threshold`, `SentimentResult.as_dict` rounding, Comprehend/HF availability semantics |
| `tests/test_models.py` | 21 | `normalize_date` (7 formats incl. `date`/`datetime` objects, 3 invalid), `parse_review` (6 invalid payloads), `parse_filters` (defaults, case-insensitive sentiment, bad values), `ReviewFilters` |
| `tests/test_cleaning_keywords.py` | 9 | `clean_text` (URLs, HTML tags, mentions, emojis, entities, casing, whitespace, 1-char drop, empty result), `tokenize` stopwords, `extract_keywords` bigram weighting, document-frequency counts |
| `tests/test_analytics.py` | 9 | `summarize` (counts, shares, ratings, date range, unknown business type, empty input), `trends` (month/day buckets, unprocessed handling, bad period), `top_keywords` (ordering, sentiment subset, serialised keywords) |
| `tests/test_storage.py` | 9 | SQLite backend: insert/get/count/ping, prepare defaults, idempotent re-ingest (update vs skip-after-process), sentiment write-back (all fields), unprocessed listing, every query filter |
| `tests/test_handlers.py` | 26 | Lambda router: health/engines routes, 404 route + method, `POST /reviews` (201 + returned id, 400 paths), `GET /reviews/{id}` path fallback, bulk CSV upload row accounting, S3-event ingest via local object store (200 + 404), processing (labels written back, 404/503/400 paths), summary/trends/keywords validation |
| `tests/test_api_e2e.py` | 4 | **End-to-end over HTTP**: FastAPI `TestClient` → same `lambda_handler` → storage → JSON. Full journey (serve `/ui/` → store 3 reviews → process → all read endpoints → CSV upload → filter by sentiment → engine switch), all error paths, static assets, S3-event round trip |
| `tests/test_metrics.py` | 8 | The experiment metric definitions themselves: perfect/known examples, macro-F1 by hand, zero-support & never-predicted classes, length/label errors, report shape |
| `tests/test_cost_model.py` | 5 | Cost-model arithmetic: per-1M price division, small-workload sanity, free-tier residual = only never-waived items, linear scaling, t3.micro/Comprehend constants |

Total: **105 tests**.

## 2. End-to-end tests

- **`tests/test_api_e2e.py` (4 tests, in-process HTTP)** — runs the complete pipeline
  through the real FastAPI app: upload → classify → query → filter → switch engine,
  plus every 400/404/503 error path and the `/ui/` dashboard assets.
- **`scripts/e2e_dashboard.py` (browser E2E, from Part 3)** — Playwright headless
  Chromium against the live server: **9/9 checks passed** (KPIs, 4 charts, table,
  free-tier panel, negative filter, live-analyze flow, CSV upload, dark mode,
  0 px mobile overflow). Documented in `PROJECT_CONTEXT.md` Part 3 recap.

## 3. Bugs found and fixed while writing the tests

Real defects the tests caught (all fixed and covered now):

1. **`POST /process` accepted `limit: 0` silently** — `int(body.get("limit") or default)`
   treated `0` as falsy and fell back to the default batch size. Now `0`,
   non-numeric, and out-of-range limits return **400** (`src/handlers/processing.py`);
   covered by `test_process_rejects_bad_limit_and_body`.
2. **Case-sensitive sentiment filter** — `?sentiment=POSITIVE` returned 400 because
   the lowercasing validator ran *after* the `Literal` check. The validator now runs
   `mode="before"` (`src/models.py`); covered by `test_parse_filters_is_case_insensitive_on_sentiment`.
3. **`prepare_record` could violate the schema** — records inserted without `source`
   failed with `NOT NULL constraint failed: reviews.source`. Defaults to `"unknown"`
   now (`src/storage/base.py`); covered by `test_prepare_record_fills_defaults`.
4. **Cost model multiplied per-1M prices by raw counts** — an early experiment run
   reported **$2,606/month for 1,000 reviews** because DynamoDB/Lambda request
   prices were applied per unit instead of per million. Fixed with an explicit
   `divisor` per component (`experiments/run_cost_model.py`) and locked by
   `tests/test_cost_model.py` so the arithmetic can never silently regress.

(An earlier defect found by the Part 3 browser E2E — `POST /reviews` not returning
the generated `review_id` — is covered by `test_single_review_created_with_id`.)

## 4. How to rerun

```powershell
cd Cloud_Project
.\.venv\Scripts\activate.ps1      # or call .venv\Scripts\python.exe directly
python -m pytest                  # whole suite (~12 s, offline, no cloud creds)
python -m pytest tests/test_api_e2e.py -v    # end-to-end only
ruff check tests src scripts experiments
```

Every test runs against a **fresh temp SQLite database** (autouse fixture in
`tests/conftest.py`), so the suite never touches `data/reviews.db` and needs no
network access or credentials.

## 5. Notes / limits

- The suite tests SQLite + offline engines (VADER, TextBlob). The DynamoDB and
  Comprehend adapters are code-reviewed but **not executed** (no AWS credentials
  by design — see `ASSUMPTIONS.md` A11); their unavailability paths *are* tested.
- The Hugging Face engine's availability branch is tested both ways; constructing
  the real model is exercised in the experiments (`experiments/`), not in unit tests,
  to keep the suite offline and fast.
