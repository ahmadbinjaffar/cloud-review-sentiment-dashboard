"""Experiment E — ablation: preprocessing effect + neutral-threshold sweep.

1) preprocessing: raw text vs clean_text() at the default threshold (0.15),
   for every available engine.
2) neutral threshold: VADER compound / TextBlob polarity band swept over
   {0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50} on cleaned text.
   (Hugging Face is included in 1 only: its threshold is read from settings at
   construction, and re-loading DistilBERT per threshold is not worth it.)

Outputs: results/ablation_preprocessing.csv, results/ablation_threshold.csv,
results/ablation_metadata.json, figures/ablation_preprocessing.png,
figures/ablation_threshold.png.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib.pyplot as plt
import pandas as pd

from experiments.common import (
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
from experiments.metrics import accuracy, macro_f1

THRESHOLDS = (0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.50)
SWEEP_ENGINES = ("vader", "textblob")


def score(y_true: list[str], preds: list[str]) -> dict:
    neutral_share = preds.count("neutral") / len(preds) if preds else 0.0
    return {
        "accuracy": round(accuracy(y_true, preds), 4),
        "macro_f1": round(macro_f1(y_true, preds), 4),
        "neutral_share": round(neutral_share, 4),
    }


def main() -> None:
    seed_everything()
    from src.cleaning import clean_text

    df = load_corpus()
    y_true = df["star_label"].tolist()
    raw_texts = df["text"].tolist()
    cleaned_texts = [clean_text(t) for t in raw_texts]
    empty_after_clean = sum(1 for t in cleaned_texts if not t)
    availability = engine_availability()
    engines = [n for n in ("vader", "textblob", "huggingface") if availability[n][0]]
    print(f"corpus: {len(df)} reviews, {empty_after_clean} empty after cleaning")
    print("engines:", engines)

    # ---- 1) preprocessing ablation (default threshold) ----------------
    preproc_rows = []
    for name in engines:
        engine = build_engine(name)
        preds_raw = [engine.analyze(t).label for t in raw_texts]
        preds_clean = [engine.analyze(t).label for t in cleaned_texts]
        for prep, preds in (("raw", preds_raw), ("clean_text", preds_clean)):
            row = {"engine": name, "preprocessing": prep, **score(y_true, preds)}
            preproc_rows.append(row)
            print(f"{name:12s} {prep:11s} acc={row['accuracy']} macro_f1={row['macro_f1']} "
                  f"neutral={row['neutral_share']}")
    preproc_df = pd.DataFrame(preproc_rows)
    print("wrote", write_csv(preproc_df, "ablation_preprocessing.csv"))

    # ---- 2) neutral-threshold sweep (cleaned text) ---------------------
    sweep_rows = []
    for name in SWEEP_ENGINES:
        if not availability[name][0]:
            continue
        engine_cls = type(build_engine(name))
        for threshold in THRESHOLDS:
            engine = engine_cls(neutral_threshold=threshold)
            preds = [engine.analyze(t).label for t in cleaned_texts]
            row = {"engine": name, "threshold": threshold, **score(y_true, preds)}
            sweep_rows.append(row)
            print(f"{name:8s} thr={threshold:<5} acc={row['accuracy']} "
                  f"macro_f1={row['macro_f1']} neutral={row['neutral_share']}")
    sweep_df = pd.DataFrame(sweep_rows)
    print("wrote", write_csv(sweep_df, "ablation_threshold.csv"))

    write_json({
        "metadata": run_metadata(),
        "thresholds": list(THRESHOLDS),
        "preprocessing_engines": engines,
        "sweep_engines": [n for n in SWEEP_ENGINES if availability[n][0]],
        "empty_after_cleaning": empty_after_clean,
        "ground_truth": "rating 1-2=negative, 3=neutral, 4-5=positive",
        "note": "same corpus and labels as the model comparison; ablation only changes "
                "preprocessing / neutral band",
    }, "ablation_metadata.json")

    # ---- figures -------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.6, 3.9))
    for name in engines:
        sub = preproc_df[preproc_df["engine"] == name]
        xs = [0, 1]
        ax1.plot(xs, sub["accuracy"], "o-", label=name)
        ax2.plot(xs, sub["macro_f1"], "o-", label=name)
    for ax, metric, title in ((ax1, "accuracy", "Accuracy"),
                              (ax2, "macro_f1", "Macro-F1")):
        ax.set_xticks([0, 1], ["raw text", "clean_text()"])
        ax.set_ylim(0, 1.05)
        ax.legend(fontsize=8)
        style_axes(ax, f"{metric} — preprocessing ablation", "", metric)
    fig.suptitle("Effect of text preprocessing on star-label agreement",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    print("wrote", save_fig(fig, "ablation_preprocessing.png"))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.6, 3.9))
    for name in sweep_df["engine"].unique():
        sub = sweep_df[sweep_df["engine"] == name]
        ax1.plot(sub["threshold"], sub["accuracy"], "o-", label=name)
        ax1.plot(sub["threshold"], sub["macro_f1"], "s--", label=f"{name} macro-F1")
        ax2.plot(sub["threshold"], sub["neutral_share"], "o-", label=name)
    for t in THRESHOLDS:
        ax1.axvline(t, color="grey", alpha=0.15, lw=0.8)
    ax1.set_ylim(0, 1.05)
    ax1.legend(fontsize=7, ncol=2)
    style_axes(ax1, "Accuracy (solid) and macro-F1 (dashed) vs threshold",
               "neutral threshold", "score")
    ax2.set_ylim(0, 1.0)
    ax2.legend(fontsize=8)
    style_axes(ax2, "Share of reviews labelled neutral", "neutral threshold", "neutral share")
    fig.suptitle("Effect of the neutral-class threshold (cleaned text)",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()
    print("wrote", save_fig(fig, "ablation_threshold.png"))
    print("ablation DONE")


if __name__ == "__main__":
    main()
