"""Experiment A — model comparison: engine accuracy vs star-derived labels.

Ground truth from the brief: rating 1-2 = negative, 3 = neutral, 4-5 = positive.
Every available engine classifies the cleaned corpus; metrics come from
experiments/metrics.py (verified by tests/test_metrics.py).
Outputs: results/model_comparison_*.csv|json, figures/model_comparison_*.png,
figures/confusion_matrix_<engine>.png.
"""
from __future__ import annotations

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
    CLASSES_ORDER,
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
from experiments.metrics import report

ENGINE_ORDER = ("vader", "textblob", "huggingface", "comprehend")


def main() -> None:
    seed_everything()
    from src.cleaning import clean_text

    df = load_corpus()
    y_true = df["star_label"].tolist()
    texts = df["text"].tolist()

    availability = engine_availability()
    runs = [n for n in ENGINE_ORDER if availability[n][0]]
    unavailable = {n: availability[n][1] for n in ENGINE_ORDER if not availability[n][0]}

    print(f"corpus: {len(df)} reviews")
    print("star-label distribution:", {c: y_true.count(c) for c in CLASSES_ORDER})
    print("engines available:", runs)
    print("engines unavailable:", unavailable)

    t0 = time.perf_counter()
    cleaned = [clean_text(t) for t in texts]
    clean_s = time.perf_counter() - t0
    print(f"preprocessing (clean_text): {clean_s:.2f}s")

    predictions: dict[str, list[str]] = {}
    predict_s: dict[str, float] = {}
    for name in runs:
        engine = build_engine(name)
        t0 = time.perf_counter()
        predictions[name] = [engine.analyze(t).label for t in cleaned]
        predict_s[name] = time.perf_counter() - t0
        print(f"{name}: {len(texts)} predictions in {predict_s[name]:.1f}s")

    # ---- metrics table -------------------------------------------------
    rows = []
    for name in runs:
        result = report(y_true, predictions[name])
        row = {
            "engine": name,
            "n": result["n"],
            "accuracy": round(result["accuracy"], 4),
            "macro_precision": round(result["macro_precision"], 4),
            "macro_recall": round(result["macro_recall"], 4),
            "macro_f1": round(result["macro_f1"], 4),
            "predict_seconds": round(predict_s[name], 2),
            "ms_per_review": round(predict_s[name] / result["n"] * 1000, 3),
        }
        for cls in CLASSES_ORDER:
            scores = result["per_class"][cls]
            row[f"precision_{cls}"] = round(scores["precision"], 4)
            row[f"recall_{cls}"] = round(scores["recall"], 4)
            row[f"f1_{cls}"] = round(scores["f1"], 4)
            row[f"support_{cls}"] = scores["support"]
        rows.append(row)
        print(f"  -> accuracy={row['accuracy']}  macro_f1={row['macro_f1']}")
    metrics_df = pd.DataFrame(rows)
    print("wrote", write_csv(metrics_df, "model_comparison_metrics.csv"))

    # ---- confusion matrices (long format) -----------------------------
    conf_rows = []
    for name in runs:
        matrix = report(y_true, predictions[name])["confusion_matrix"]
        for i, true_label in enumerate(CLASSES_ORDER):
            for j, pred_label in enumerate(CLASSES_ORDER):
                conf_rows.append({"engine": name, "true_label": true_label,
                                  "predicted_label": pred_label, "count": matrix[i][j]})
    print("wrote", write_csv(pd.DataFrame(conf_rows), "model_comparison_confusion.csv"))

    # ---- per-review predictions ---------------------------------------
    pred_df = df[["review_id", "rating", "star_label"]].copy()
    for name in runs:
        pred_df[f"pred_{name}"] = predictions[name]
    print("wrote", write_csv(pred_df, "model_comparison_predictions.csv"))

    write_json({
        "metadata": run_metadata(),
        "engines_run": runs,
        "engines_unavailable": unavailable,
        "cleaning_seconds": round(clean_s, 3),
        "predict_seconds": {k: round(v, 2) for k, v in predict_s.items()},
        "label_rule": "rating 1-2=negative, 3=neutral, 4-5=positive",
        "preprocessing": "clean_text() applied before analysis (production path)",
    }, "model_comparison_metadata.json")

    # ---- figures -------------------------------------------------------
    fig, ax = plt.subplots(figsize=(6.6, 3.8))
    x = np.arange(len(runs))
    w = 0.35
    acc = [r["accuracy"] for r in rows]
    f1 = [r["macro_f1"] for r in rows]
    bars1 = ax.bar(x - w / 2, acc, w, label="Accuracy", color="#2563eb")
    bars2 = ax.bar(x + w / 2, f1, w, label="Macro-F1", color="#7c3aed")
    for b in list(bars1) + list(bars2):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.012,
                f"{b.get_height():.3f}", ha="center", fontsize=7)
    ax.set_xticks(x)
    ax.set_xticklabels(runs)
    ax.set_ylim(0, 1.12)
    style_axes(ax, "Engine accuracy vs star-derived labels (1,214 reviews)",
               "Engine", "Score")
    ax.legend(fontsize=8)
    print("wrote", save_fig(fig, "model_comparison_scores.png"))

    for name in runs:
        matrix = np.array(report(y_true, predictions[name])["confusion_matrix"])
        fig, ax = plt.subplots(figsize=(4.4, 3.8))
        im = ax.imshow(matrix, cmap="Blues")
        for i in range(3):
            for j in range(3):
                ax.text(j, i, str(matrix[i, j]), ha="center", va="center",
                        color="white" if matrix[i, j] > matrix.max() * 0.6 else "black",
                        fontsize=10)
        ax.set_xticks(range(3), CLASSES_ORDER, fontsize=8)
        ax.set_yticks(range(3), CLASSES_ORDER, fontsize=8)
        ax.set_xlabel("Predicted")
        ax.set_ylabel("True (stars)")
        ax.set_title(f"Confusion matrix — {name}", fontsize=10, fontweight="bold")
        fig.colorbar(im, ax=ax, shrink=0.75, label="reviews")
        print("wrote", save_fig(fig, f"confusion_matrix_{name}.png"))

    print("model comparison DONE")


if __name__ == "__main__":
    main()
