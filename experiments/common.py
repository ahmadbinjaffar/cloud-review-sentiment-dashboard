"""Shared helpers for the Part-4 experiments: corpus, labels, seeds, outputs.

Every experiment imports from here so all runs share one seed (42), one
star-derived labelling rule, and one output layout:
  - raw numbers -> results/*.csv | *.json
  - charts     -> figures/*.png (300 dpi)
"""
from __future__ import annotations

import json
import platform
import random
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless, no GUI needed

import matplotlib.pyplot as plt
import pandas as pd

try:  # consistent chart look across scripts
    plt.style.use("seaborn-v0_8-whitegrid")
except OSError:  # pragma: no cover - style name differs across matplotlib versions
    pass

SEED = 42
ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
FIGURES = ROOT / "figures"
CORPUS_CSV = ROOT / "data" / "reviews.csv"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Class colours used by every chart
COLORS = {"positive": "#16a34a", "neutral": "#d97706", "negative": "#dc2626"}
CLASSES_ORDER = ("positive", "neutral", "negative")  # metrics/confusion axis order


def seed_everything(seed: int = SEED) -> None:
    """Fix all RNGs used by the experiments."""
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:  # pragma: no cover - numpy is a hard dep of pandas
        pass


def load_corpus() -> pd.DataFrame:
    """The cleaned TripAdvisor corpus (1,214 reviews) with star-derived labels."""
    df = pd.read_csv(CORPUS_CSV)
    df = df.dropna(subset=["text", "rating"]).copy()
    df["rating"] = df["rating"].astype(int)
    df["star_label"] = df["rating"].map(star_label)
    return df.reset_index(drop=True)


def star_label(rating: int) -> str:
    """Brief's ground truth: 1-2 stars = negative, 3 = neutral, 4-5 = positive."""
    if rating <= 2:
        return "negative"
    if rating == 3:
        return "neutral"
    return "positive"


def write_csv(df: pd.DataFrame, name: str) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / name
    df.to_csv(path, index=False)
    return path


def write_json(payload: dict, name: str) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / name
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def save_fig(fig: plt.Figure, name: str) -> Path:
    """Save at 300 dpi (project chart standard)."""
    FIGURES.mkdir(parents=True, exist_ok=True)
    path = FIGURES / name
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return path


def style_axes(ax, title: str = "", xlabel: str = "", ylabel: str = "") -> None:
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.set_xlabel(xlabel, fontsize=9)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.tick_params(labelsize=8)
    ax.grid(True, axis="y", alpha=0.3)


def engine_availability() -> dict[str, tuple[bool, str]]:
    """{engine: (available, reason)} for the four registered engines."""
    from src.sentiment import ENGINES

    return {name: cls.is_available() for name, cls in ENGINES.items()}


def build_engine(name: str):
    """Instantiate an engine through the production factory (raises if unavailable)."""
    from src.sentiment import get_engine

    return get_engine(name)


def run_metadata(extra: dict | None = None) -> dict:
    """Provenance block written next to every experiment's raw results."""
    meta = {
        "date": "2026-10-15",
        "seed": SEED,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor() or "unknown",
        "cpu_count": __import__("os").cpu_count(),
        "corpus": str(CORPUS_CSV.name),
        "corpus_rows": len(load_corpus()),
    }
    if extra:
        meta.update(extra)
    return meta
