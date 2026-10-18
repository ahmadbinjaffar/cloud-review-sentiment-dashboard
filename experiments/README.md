# experiments/ — Part 4 test-bench

Five experiments behind `RESULTS_SUMMARY.md`. All raw numbers go to
`results/*.csv|json`, all charts to `figures/*.png` (300 dpi). **Nothing is
fabricated**: every number is produced by these scripts on this machine.

| # | Script | Question | Key outputs |
|---|--------|----------|-------------|
| a | `run_model_comparison.py` | How accurate is each engine vs star labels (1-2★ neg, 3★ neu, 4-5★ pos)? | `results/model_comparison_metrics.csv`, `model_comparison_confusion.csv`, `model_comparison_predictions.csv`, `model_comparison_metadata.json`; `figures/model_comparison_scores.png`, `figures/confusion_matrix_<engine>.png` |
| b | `run_latency.py` | Average / p50 / p95 / p99 latency per engine; cold vs warm start | `results/latency_summary.csv`, `latency_raw.csv`, `latency_metadata.json`; `figures/latency_cold_start.png`, `latency_warm_percentiles.png` |
| c | `run_throughput.py` | Batch ingestion of 100 / 1,000 / 10,000 reviews: time, reviews/s, memory | `results/throughput_ingestion.csv`, `throughput_ingestion.json`; `figures/throughput_ingestion.png` |
| d | `run_cost_model.py` | Monthly cost of 1K / 10K / 100K / 1M reviews: AWS free tier vs after, t3.micro, managed SaaS | `results/cost_model.csv`, `cost_model_detail.json`, **`cost_sources.json`** (every price + URL + access date); `figures/cost_model.png` |
| e | `run_ablation.py` | Effect of text preprocessing and the neutral-class threshold on accuracy | `results/ablation_preprocessing.csv`, `ablation_threshold.csv`, `ablation_metadata.json`; `figures/ablation_preprocessing.png`, `ablation_threshold.png` |

Support modules (also covered by the test suite):

- `common.py` — corpus loading, star-label rule, seed (**42**), output writers, chart style.
- `metrics.py` — accuracy / precision / recall / macro-F1 / confusion matrix,
  textbook definitions, verified by `tests/test_metrics.py`.
- `_latency_worker.py` — subprocess used to time cold starts.
- `_logs/` — stdout+stderr of the last full run, one file per experiment.

## Prerequisites

```powershell
cd Cloud_Project
# .venv with requirements.txt installed; experiments additionally need:
.venv\Scripts\python.exe -m pip install matplotlib psutil
# Optional — only for the Hugging Face engine (offline DistilBERT, ~270 MB model download):
.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python.exe -m pip install transformers
```

No cloud credentials are needed. Without `torch`/`transformers`, experiment (a)
and (e) simply skip Hugging Face and record the reason in the metadata JSON —
the run still completes.

## How to rerun

Run from `Cloud_Project/` in order (d reads c's throughput CSV if it exists):

```powershell
.venv\Scripts\python.exe experiments\run_model_comparison.py   # a — ~1-3 min
.venv\Scripts\python.exe experiments\run_ablation.py           # e — ~1-3 min
.venv\Scripts\python.exe experiments\run_latency.py            # b — ~1-2 min
.venv\Scripts\python.exe experiments\run_throughput.py         # c — ~1-2 min
.venv\Scripts\python.exe experiments\run_cost_model.py         # d — ~30 s
```

Or everything at once:

```powershell
.\scripts\run_experiments.ps1
```

Each script prints the numbers it writes and finishes with `<name> DONE`.

## Fixed settings

- **Seed 42** (`experiments/common.py::SEED`) — sampling in the latency run and
  every RNG draw; the other experiments are deterministic over the full corpus.
- **Corpus**: `data/reviews.csv`, 1,214 cleaned TripAdvisor reviews (MIT).
- **Ground truth**: star rating 1-2 → negative, 3 → neutral, 4-5 → positive (brief).
- **Preprocessing**: production path `clean_text()` unless the run is the
  preprocessing ablation arm (`raw`).
- Charts: `matplotlib` (Agg), `seaborn-v0_8-whitegrid`, saved at **300 dpi**.

## Things to know before quoting the numbers

1. **Cold start is local**: a fresh Python subprocess (interpreter + engine
   construction + first call). It is a *proxy* for a Lambda cold start, not an
   AWS measurement.
2. **Throughput input** repeats the 1,214 real reviews in date-shifted blocks so
   dedupe keys stay unique — a synthetic load pattern built from real rows
   (documented in `throughput_ingestion.json`).
3. **Cost model**: every price carries a source URL and the access date
   `2026-10-15` in `results/cost_sources.json`. Items that could not be
   verified from a vendor page are marked `UNVERIFIED` (MonkeyLearn's $299/mo
   starting price). Compute usage inside the AWS model is *measured* by the
   scripts (ms/review, bytes/review), not guessed.
4. **DynamoDB free tier** covers *provisioned* capacity only; the model uses
   on-demand tables, so request charges apply even inside the free tier — this
   is reflected in the "AWS free tier" row and stated in the JSON.
5. Engines that are unavailable (Comprehend without AWS credentials) are never
   scored; the reason is recorded instead.
