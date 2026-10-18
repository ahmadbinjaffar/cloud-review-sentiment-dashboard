"""VADER engine (lexicon + rules, no network, no credentials)."""
from __future__ import annotations

from ..config import get_settings
from .base import SentimentEngine, SentimentResult


class VaderEngine(SentimentEngine):
    name = "vader"

    def __init__(self, neutral_threshold: float | None = None):
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        settings = get_settings()
        self._threshold = neutral_threshold if neutral_threshold is not None else settings.neutral_threshold
        self._analyzer = SentimentIntensityAnalyzer()

    def analyze(self, text: str) -> SentimentResult:
        scores = self._analyzer.polarity_scores(text)
        pos, neg, neu = float(scores["pos"]), float(scores["neg"]), float(scores["neu"])
        compound = float(scores["compound"])
        if compound >= self._threshold:
            label, confidence = "positive", max(pos, compound)
        elif compound <= -self._threshold:
            label, confidence = "negative", max(neg, abs(compound))
        else:
            label, confidence = "neutral", max(neu, 1.0 - abs(compound))
        return SentimentResult(
            label=label,
            confidence=min(confidence, 1.0),
            scores={"positive": pos, "negative": neg, "neutral": neu, "compound": compound},
            engine=self.name,
        )

    @classmethod
    def is_available(cls) -> tuple[bool, str]:
        try:
            import vaderSentiment  # noqa: F401
        except ImportError:
            return False, "vaderSentiment not installed (pip install vaderSentiment)"
        return True, "ok"
