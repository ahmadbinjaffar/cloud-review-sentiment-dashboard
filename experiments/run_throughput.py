"""Experiment C — batch ingestion throughput and memory at 100 / 1,000 / 10,000 reviews.

Input: the 1,214 real reviews repeated in date-shifted blocks so every
(date, text) key stays unique (synthetic load pattern, seed-independent
round-robin, clearly labelled in the metadata). Each batch runs twice into a
fresh temp SQLite DB:
  pass A — wall time + peak RSS (no tracemalloc overhead)
  pass B — tracemalloc peak (Python-heap memory)

Outputs: results/throughput_ingestion.csv, results/throughput_ingestion.json,
figures/throughput_ingestion.png.
"""
from __future__ import annotations

import csv
import io
import sys
import tempfile
import threading
import time
import tracemalloc
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import psutil

from experiments.common import (
    load_corpus,
    run_metadata,
    save_fig,
    seed_everything,
    style_axes,
    write_csv,
    write_json,
)

BATCH_SIZES = (100, 1000, 10000)


class RssSampler:
    """Samples this process's resident memory on a thread while a batch runs."""

    def __init__(self, interval: float = 0.005):
        self._proc = psutil.Process()
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self.start_rss = self._proc.memory_info().rss
        self.peak_rss = self.start_rss

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.peak_rss = max(self.peak_rss, self._proc.memory_info().rss)
            self._stop.wait(self._interval)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> float:
        self._stop.set()
        self._thread.join(timeout=2)
        return self.peak_rss


def build_csv_content(df: pd.DataFrame, n: int) -> str:
    """n reviews: real corpus rows in round-robin, date shifted 366 d per block."""
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["date", "rating", "text", "business_type", "business_name"])
    records = df[["date", "rating", "text", "business_type", "business_name"]].to_dict("records")
    for i in range(n):
        src = records[i % len(records)]
        block = i // len(records)
        shifted = date.fromisoformat(src["date"]) + timedelta(days=366 * block)
        writer.writerow([shifted.isoformat(), src["rating"], src["text"],
                         src["business_type"] or "", src["business_name"] or ""])
    return buf.getvalue()


def run_batch(content: str, with_tracemalloc: bool) -> dict:
    """parse_records + insert_reviews against a fresh temp SQLite DB."""
    from src.handlers.ingestion import parse_records
    from src.storage.sqlite_store import SQLiteStorage

    with tempfile.TemporaryDirectory(prefix="thrput_") as td:
        store = SQLiteStorage(str(Path(td) / "bench.db"))
        sampler = RssSampler()
        sampler.start()
        if with_tracemalloc:
            tracemalloc.start()
        t0 = time.perf_counter()
        parsed = parse_records(content=content, filename="bench.csv")
        stored = store.insert_reviews(parsed["records"])
        elapsed = time.perf_counter() - t0
        heap_peak = 0
        if with_tracemalloc:
            _, heap_peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        rss_peak = sampler.stop()
        store.close()

    return {
        "seconds": elapsed,
        "total_rows": parsed["total"],
        "valid_records": len(parsed["records"]),
        "invalid_rows": len(parsed["invalid"]),
        "duplicates": parsed["duplicates"],
        "inserted": stored["inserted"],
        "skipped": stored["skipped"],
        "tracemalloc_peak_mb": heap_peak / 1e6,
        "rss_start_mb": sampler.start_rss / 1e6,
        "rss_peak_mb": rss_peak / 1e6,
    }


def main() -> None:
    seed_everything()
    df = load_corpus()
    print(f"corpus: {len(df)} real reviews used as load-test source")

    rows = []
    for n in BATCH_SIZES:
        content = build_csv_content(df, n)
        print(f"--- batch {n}: pass A (timing) ---")
        a = run_batch(content, with_tracemalloc=False)
        print(f"--- batch {n}: pass B (tracemalloc) ---")
        b = run_batch(content, with_tracemalloc=True)
        row = {
            "batch_size": n,
            "timing_seconds": round(a["seconds"], 4),
            "reviews_per_second": round(n / a["seconds"], 1),
            "inserted": a["inserted"],
            "invalid_rows": a["invalid_rows"],
            "duplicates_in_file": a["duplicates"],
            "rss_start_mb": round(a["rss_start_mb"], 1),
            "rss_peak_mb": round(a["rss_peak_mb"], 1),
            "rss_delta_mb": round(a["rss_peak_mb"] - a["rss_start_mb"], 1),
            "mem_pass_seconds": round(b["seconds"], 4),
            "tracemalloc_peak_mb": round(b["tracemalloc_peak_mb"], 1),
        }
        rows.append(row)
        print(f"batch {n}: {row['timing_seconds']}s -> {row['reviews_per_second']} reviews/s, "
              f"rss_peak={row['rss_peak_mb']}MB, heap_peak={row['tracemalloc_peak_mb']}MB")

    out = pd.DataFrame(rows)
    print("wrote", write_csv(out, "throughput_ingestion.csv"))
    write_json({
        "metadata": run_metadata(),
        "method": "parse_records (CSV) + SQLiteStorage.insert_reviews, fresh temp DB per batch",
        "input_pattern": "1,214 real reviews repeated round-robin; date shifted +366 days per "
                         "repetition so (date, text) dedupe keys stay unique — synthetic load "
                         "pattern built from real rows",
        "pass_a": "wall time + peak RSS (5 ms sampler), no tracemalloc",
        "pass_b": "tracemalloc Python-heap peak (adds overhead; its seconds are not the benchmark)",
        "batch_sizes": list(BATCH_SIZES),
        "rows": rows,
    }, "throughput_ingestion.json")

    # ---- figure --------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.2, 3.8))
    labels = [str(s) for s in BATCH_SIZES]
    x = np.arange(len(labels))

    bars = ax1.bar(x, out["timing_seconds"], color="#2563eb")
    for b, v in zip(bars, out["timing_seconds"]):
        ax1.text(b.get_x() + b.get_width() / 2, b.get_height(), f"{v:g}s",
                 ha="center", va="bottom", fontsize=8)
    ax1.set_xticks(x, labels)
    style_axes(ax1, "Ingestion wall time", "reviews per batch", "seconds")

    bars = ax2.bar(x, out["reviews_per_second"], color="#16a34a")
    for b, v in zip(bars, out["reviews_per_second"]):
        ax2.text(b.get_x() + b.get_width() / 2, b.get_height(), f"{v:,.0f}",
                 ha="center", va="bottom", fontsize=8)
    ax2.set_xticks(x, labels)
    style_axes(ax2, "Ingestion throughput", "reviews per batch", "reviews / second")

    fig.suptitle("Batch ingestion: time and throughput (CSV parse + SQLite insert)",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    print("wrote", save_fig(fig, "throughput_ingestion.png"))
    print("throughput DONE")


if __name__ == "__main__":
    main()
