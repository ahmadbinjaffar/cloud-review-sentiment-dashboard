# RESULTS_SUMMARY — Part 4 experiments (2026-10-15)

All numbers below are written by the scripts in `experiments/` and stored in
`results/` — nothing is estimated by hand or invented. Machine: Windows 11,
Python 3.13.7, CPU-only (no GPU), seed **42**. Corpus: 1,214 cleaned TripAdvisor
reviews (`data/reviews.csv`). Ground truth: stars 1-2 → negative, 3 → neutral,
4-5 → positive → **1,190 positive / 12 neutral / 12 negative** (the skew is a
property of the source data, A12/A19).

---

## a. Model comparison (`results/model_comparison_*.csv`)

| Engine | Accuracy | Macro-P | Macro-R | **Macro-F1** | F1 neutral | F1 negative | ms/review |
|---|---:|---:|---:|---:|---:|---:|---:|
| **vader** | **0.9712** | 0.4860 | 0.4677 | **0.4757** | 0.0769 | **0.3636** | 0.219 |
| textblob | 0.9662 | **0.5459** | 0.4936 | 0.4486 | **0.2174** | 0.1429 | 0.639 |
| huggingface (DistilBERT-SST2, local) | 0.9596 | 0.3974 | **0.6013** | 0.4346 | 0.0000 | 0.3226 | 49.828 |
| comprehend | *not run — no AWS credentials (recorded in metadata JSON)* | | | | | | |

Read the confusion matrices before the headline accuracies: 98 % of the corpus
is positive, so a "always positive" classifier already scores 0.98. What the
engines actually differ in:

- **Hugging Face finds the negatives**: recall 0.8333 (10 of 12 true negatives
  caught — see `figures/confusion_matrix_huggingface.png`) but it **never**
  predicts neutral (0 of 12) — the SST-2 model is binary by construction, mapped
  through the compound/threshold rule (0 neutral predictions).
- **VADER is the best all-rounder on this skewed set**: highest accuracy and
  macro-F1, only engine that is reasonable on all three classes, and it is
  ~228× faster per review than DistilBERT (0.219 ms vs 49.8 ms).
- **TextBlob** has the best positive-class precision (0.9907) but almost no
  negative recall (1 of 12).
- Scoring 1,214 reviews took 0.27 s (vader), 0.78 s (textblob), 60.5 s
  (huggingface, CPU, batch-of-1 calls).

→ Decision: VADER stays the default engine (matches Part 2/3 choice); HF is the
accuracy-oriented alternative when credentials/GPU are available.

## b. Latency (`results/latency_summary.csv`, `latency_raw.csv`)

Warm, 500 timed requests per engine after 10 warm-ups (ms):

| Engine | mean | p50 | p95 | p99 | min | max |
|---|---:|---:|---:|---:|---:|---:|
| vader | 0.476 | 0.439 | 0.854 | 1.065 | 0.101 | 1.202 |
| textblob | 1.229 | 1.140 | 1.848 | 2.565 | 0.443 | 4.496 |
| huggingface | 48.229 | 45.785 | 73.136 | 91.760 | 29.002 | 121.965 |

Cold start (fresh Python subprocess — interpreter + engine init + first call;
a **local proxy** for a Lambda cold start, not an AWS measurement, A21):

| Engine | engine construction | first analyze | whole process → first result |
|---|---:|---:|---:|
| vader | 0.050 s | 0.0002 s | 3.418 s |
| textblob | 0.787 s | 0.046 s | 3.836 s |
| huggingface | 18.576 s | 0.035 s | 22.763 s |

DistilBERT's first *analysis* is fast (35 ms), but loading torch+model costs
~18.6 s — the dominant cold-start term. The lexicon engines are effectively
instant. Charts: `figures/latency_cold_start.png`, `figures/latency_warm_percentiles.png`.

## c. Throughput & scalability (`results/throughput_ingestion.csv`)

Batch ingestion = CSV parse + SQLite insert, fresh temp DB per batch
(input: real reviews repeated in date-shifted blocks so dedupe keys stay unique
— synthetic load pattern, A22):

| Batch | wall time | reviews/s | inserted | invalid | peak RSS | tracemalloc heap peak |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 0.0132 s | 7,550 | 100 | 0 | 117.3 MB | 0.3 MB |
| 1,000 | 0.0574 s | 17,416 | 1,000 | 0 | 121.0 MB | 2.1 MB |
| 10,000 | 0.580 s | 17,242 | 10,000 | 0 | 148.0 MB | 21.6 MB |

Throughput is stable ~17.4k reviews/s from 1k → 10k (linear scaling; the small
100-row batch is dominated by fixed costs, hence lower). Memory grows ~2 MB per
10k rows of heap; RSS stays <150 MB. 0 invalid rows / 0 duplicates — the input
pattern guarantees unique keys.

## d. Cost model (`results/cost_model.csv`, `cost_model_detail.json`, `cost_sources.json`)

Monthly cost of ingesting + classifying + storing + dashboarding N reviews.
AWS rows use **measured** pipeline inputs (**7.47 ms/review** end-to-end VADER
processing incl. write-back; **732 bytes/review** stored) and published prices
accessed **2026-10-15, us-east-1** — every price has a source URL in
`results/cost_sources.json` (MonkeyLearn's $299 is explicitly **UNVERIFIED**,
third-party guide only).

| Reviews/month | AWS free tier | AWS pay-as-you-go | EC2 t3.micro (always-on) | Comprehend API | MonkeyLearn SaaS |
|---:|---:|---:|---:|---:|---:|
| 1,000 | **$0.0025** | $0.0034 | $8.23 | $0.30 | $299 |
| 10,000 | $0.025 | $0.0336 | $8.23 | $3.00 | $299 |
| 100,000 | $0.25 | $0.3352 | $8.23 | $30.05 | $299 |
| 1,000,000 | **$2.50** | **$3.3513** | $8.23 | **$300.49** | $299 |

What the numbers say:

- The serverless pipeline costs **pennies** at every modelled volume — even with
  *zero* free-tier allowance it is $3.35/month at 1M reviews, dominated by
  DynamoDB on-demand requests ($1.25 writes + $1.25 reads) and CloudWatch logs.
- The "free tier" row is **not** always $0 because DynamoDB's 25 WCU/RCU
  allowance covers *provisioned* tables only; our on-demand table pays per
  request (A23, source-flagged in the JSON).
- A **t3.micro ($8.23/mo) is ~3,300× more expensive** than the free-tier
  serverless path at 1K reviews and still ~2.5× the no-free-tier price at 1M —
  while adding a server to patch and no auto-scaling.
- **Comprehend scales linearly with text volume** (~$300/mo at 1M reviews,
  90× the serverless pipeline) because every 100 characters is billed.
- A flat-rate SaaS (MonkeyLearn ~$299, unverified) only makes sense above
  ~1M reviews/month versus this pipeline.
- Model assumptions (batch=200, 512 MB Lambda, warm executions, 20 dashboard
  GETs/batch, 10 read units/review, ~1 KB logs/review) are recorded in
  `cost_model_detail.json`; the free-tier row also applies API GW/S3 legacy
  12-month allowances, flagged as legacy in the sources.

Chart: `figures/cost_model.png` (log scale).

## e. Ablation (`results/ablation_preprocessing.csv`, `ablation_threshold.csv`)

**Preprocessing** (raw text vs `clean_text()`, threshold 0.15):

| Engine | raw acc / macro-F1 | cleaned acc / macro-F1 | effect |
|---|---|---|---|
| vader | 0.9638 / 0.4110 | **0.9712 / 0.4757** | cleaning helps both (+0.007 acc, +0.065 F1) |
| textblob | 0.9563 / 0.4637 | 0.9662 / 0.4486 | accuracy +0.010, macro-F1 −0.015 |
| huggingface | 0.9687 / 0.4646 | 0.9596 / 0.4346 | cleaning *hurts* slightly (−0.009 / −0.030) |

Cleaning clearly helps the lexicon engines (URLs/emoji/HTML otherwise pollute
their dictionaries) but mildly hurts DistilBERT — the raw transformer already
handles noise, and stripping emojis removes signal. The production pipeline
keeps cleaning because VADER is the default engine.

**Neutral-threshold sweep** (cleaned text):

- **VADER** degrades gracefully: accuracy 0.9811 (t=0.0) → 0.9712 (0.15, the
  default) → 0.9498 (0.5); macro-F1 actually *rises* to 0.4920 at t=0.5
  (more neutral predictions help the tiny neutral class); neutral share grows
  smoothly 0 % → 4.28 %.
- **TextBlob** is fragile at the top end: accuracy 0.9786 (0.0) → 0.9662 (0.15)
  → **0.6013 at 0.5** with 40.6 % of reviews forced into neutral. Its polarity
  rarely exceeds ±0.5, so a wide band swamps the labels.
- The default **0.15 is a sensible middle** for both engines; the sweep shows
  accuracy and macro-F1 trade against each other as the band widens.

Charts: `figures/ablation_preprocessing.png`, `figures/ablation_threshold.png`.

---

## Reproducing

```powershell
.\scripts\run_experiments.ps1     # or the five commands in experiments/README.md
```

Raw files: `results/*.csv|json` (15 files), charts: `figures/*.png` (10 experiment
charts + 2 report diagrams = 12 files, 300 dpi), run logs: `experiments/_logs/`.
