"""Pluggable sentiment engine interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SentimentResult:
    """Standard result every engine must return."""

    label: str  # "positive" | "negative" | "neutral"
    confidence: float  # probability-like score in [0, 1]
    scores: dict[str, float] = field(default_factory=dict)  # per-class probabilities
    engine: str = "unknown"

    def as_dict(self) -> dict:
        return {
            "sentiment": self.label,
            "confidence": round(float(self.confidence), 4),
            "scores": {k: round(float(v), 4) for k, v in self.scores.items()},
            "engine": self.engine,
        }


class SentimentEngine(ABC):
    """All engines analyse one text and return a SentimentResult."""

    name: str = "base"

    @abstractmethod
    def analyze(self, text: str) -> SentimentResult:
        """Classify text as positive/negative/neutral with confidence."""

    @classmethod
    def is_available(cls) -> tuple[bool, str]:
        """Return (available, reason). Subclasses override when a dependency can be missing."""
        return True, "ok"

    @staticmethod
    def label_from_binary(pos: float, neg: float, neutral_threshold: float) -> str:
        """3-class mapping from positive/negative probabilities (proposal rule)."""
        return "positive" if pos - neg > neutral_threshold else "negative" if neg - pos > neutral_threshold else "neutral"
