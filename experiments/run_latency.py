"""Experiment B — latency per engine: cold start (fresh subprocess) vs warm requests.

Cold start = wall time of a *fresh Python process* that imports the engine,
constructs it, and runs one analysis (a local proxy for a Lambda cold start —
this is NOT an AWS measurement). Warm = in-process requests after warm-up.

Outputs: results/latency_summary.csv, results/latency_raw.csv,
results/latency_metadata.json, figures/latency_cold_start.png,
figures/latency_warm_percentiles.png.
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from experiments.common import (
    SEED,
    build_engine,
    engine_availability,
    load_corpus,
    run_metadata,
    save_fig,
    seed_everything,
    style_axes,
    write_csv,
    write_json,
)

N_WARM = 500        # timed warm requests per engine
N_WARMUP = 10       # untimed warm-up requests
ENGINE_ORDER = ("vader", "textblob", "huggingface")


def cold_start(engine_name: str) -> dict:
    """Time engine init + first inference in a brand-new process."""
    worker = ROOT / "experiments" / "_latency_worker.py"
    t0 = time.perf_counter()
    proc = subprocess.run([sys.executable, str(worker), engine_name],
                          capture_output=True, text=True, timeout=900, cwd=ROOT,
                          check=False)
    wall_s = time.perf_counter() - t0
    if proc.returncode != 0:
        raise RuntimeError(f"cold-start worker failed for {engine_name}: {proc.stderr[-400:]}")
    for line in proc.stdout.splitlines():
        if line.startswith("WORKER_RESULT "):
            payload = json.loads(line[len("WORKER_RESULT "):])
            payload["process_wall_s"] = round(wall_s, 4)
            return payload
    raise RuntimeError(f"no WORKER_RESULT line in worker output: {proc.stdout[-400:]}")


def warm(engine_name: str, cleaned: list[str]) -> tuple[list[float], float]:
    """Timed in-process requests; returns (per-request ms, in-process init s)."""
    t0 = time.perf_counter()
    engine = build_engine(engine_name)
    init_s = time.perf_counter() - t0
    for text in cleaned[:N_WARMUP]:
        engine.analyze(text)
    rng = random.Random(SEED)
    sample = [cleaned[rng.randrange(len(cleaned))] for _ in range(N_WARM)]
    timings = []
    for text in sample:
        t0 = time.perf_counter()
        engine.analyze(text)
        timings.append((time.perf_counter() - t0) * 1000.0)
    return timings, init_s


def main() -> None:
    seed_everything()
    from src.cleaning import clean_text

    df = load_corpus()
    cleaned = [clean_text(t) for t in df["text"].tolist()]
    availability = engine_availability()
    engines = [n for n in ENGINE_ORDER if availability[n][0]]
    print("engines measured:", engines)

    summary_rows, raw_rows = [], []
    for name in engines:
        print(f"[{name}] cold start (fresh subprocess)...")
        cold = cold_start(name)
        print(f"[{name}] init={cold['init_s']}s first_call={cold['first_call_s']}s "
              f"process_wall={cold['process_wall_s']}s")

        print(f"[{name}] warm: {N_WARM} requests...")
        timings, warm_init_s = warm(name, cleaned)
        arr = np.array(timings, dtype=float)
        row = {
            "engine": name,
            "n_requests": N_WARM,
            "warm_mean_ms": round(float(arr.mean()), 3),
            "warm_p50_ms": round(float(np.percentile(arr, 50)), 3),
            "warm_p95_ms": round(float(np.percentile(arr, 95)), 3),
            "warm_p99_ms": round(float(np.percentile(arr, 99)), 3),
            "warm_min_ms": round(float(arr.min()), 3),
            "warm_max_ms": round(float(arr.max()), 3),
            "warm_process_init_s": round(warm_init_s, 3),
            "cold_init_s": cold["init_s"],
            "cold_first_call_s": cold["first_call_s"],
            "cold_process_wall_s": cold["process_wall_s"],
        }
        summary_rows.append(row)
        raw_rows.extend({"engine": name, "request": i + 1, "ms": round(v, 4)}
                        for i, v in enumerate(timings))
        print(f"[{name}] warm mean={row['warm_mean_ms']}ms p50={row['warm_p50_ms']}ms "
              f"p95={row['warm_p95_ms']}ms p99={row['warm_p99_ms']}ms")

    summary_df = pd.DataFrame(summary_rows)
    print("wrote", write_csv(summary_df, "latency_summary.csv"))
    print("wrote", write_csv(pd.DataFrame(raw_rows), "latency_raw.csv"))
    write_json({
        "metadata": run_metadata({"n_warm_requests": N_WARM, "n_warmup": N_WARMUP,
                                  "percentile_method": "numpy.percentile linear interpolation"}),
        "cold_start_definition": "fresh Python subprocess: interpreter start + engine "
                                 "construction + first analyze (local proxy for Lambda cold start)",
        "note": "timed analyze() on pre-cleaned text; preprocessing excluded",
        "engines": engines,
    }, "latency_metadata.json")

    # ---- figures -------------------------------------------------------
    labels = [r["engine"] for r in summary_rows]

    fig, ax = plt.subplots(figsize=(6.6, 3.8))
    init_ms = [r["cold_init_s"] * 1000 for r in summary_rows]
    first_ms = [r["cold_first_call_s"] * 1000 for r in summary_rows]
    wall_ms = [r["cold_process_wall_s"] * 1000 for r in summary_rows]
    x = np.arange(len(labels))
    ax.bar(x, init_ms, label="engine construction (ms)", color="#2563eb")
    ax.bar(x, first_ms, bottom=init_ms, label="first analyze (ms)", color="#f59e0b")
    for xi, (i1, i2, w) in enumerate(zip(init_ms, first_ms, wall_ms)):
        ax.text(xi, i1 + i2 + max(wall_ms) * 0.03,
                f"process total {w:.0f} ms", ha="center", fontsize=7)
    ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    style_axes(ax, "Cold start: fresh-process time to first result (log scale)",
               "Engine", "milliseconds (log)")
    ax.legend(fontsize=8)
    print("wrote", save_fig(fig, "latency_cold_start.png"))

    fig, ax = plt.subplots(figsize=(6.6, 3.8))
    metrics = ["warm_mean_ms", "warm_p50_ms", "warm_p95_ms", "warm_p99_ms"]
    pretty = ["mean", "p50", "p95", "p99"]
    width = 0.2
    colors = ["#2563eb", "#16a34a", "#f59e0b", "#dc2626"]
    for k, (metric, label, color) in enumerate(zip(metrics, pretty, colors)):
        offset = (k - 1.5) * width
        bars = ax.bar(x + offset, [r[metric] for r in summary_rows], width,
                      label=label, color=color)
        for b in bars:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() * 1.15,
                    f"{b.get_height():g}", ha="center", fontsize=6.5)
    ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    style_axes(ax, f"Warm latency percentiles over {N_WARM} requests (log scale)",
               "Engine", "ms (log)")
    ax.legend(fontsize=8, ncol=4)
    print("wrote", save_fig(fig, "latency_warm_percentiles.png"))

    print("latency DONE")


if __name__ == "__main__":
    main()
