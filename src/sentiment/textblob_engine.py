"""TextBlob engine (pattern-based polarity, no network, no credentials)."""
from __future__ import annotations

from ..config import get_settings
from .base import SentimentEngine, SentimentResult


class TextBlobEngine(SentimentEngine):
    name = "textblob"

    def __init__(self, neutral_threshold: float | None = None):
        from textblob import TextBlob

        self._TextBlob = TextBlob
        settings = get_settings()
        self._threshold = neutral_threshold if neutral_threshold is not None else settings.neutral_threshold

    def analyze(self, text: str) -> SentimentResult:
        polarity = float(self._TextBlob(text).sentiment.polarity)  # [-1, 1]
        if polarity > self._threshold:
            label = "positive"
            confidence = (1.0 + polarity) / 2.0
        elif polarity < -self._threshold:
            label = "negative"
            confidence = (1.0 - polarity) / 2.0
        else:
            label = "neutral"
            confidence = 1.0 - abs(polarity)
        return SentimentResult(
            label=label,
            confidence=round(confidence, 4),
            scores={"polarity": polarity, "subjectivity": float(self._TextBlob(text).sentiment.subjectivity)},
            engine=self.name,
        )

    @classmethod
    def is_available(cls) -> tuple[bool, str]:
        try:
            import textblob  # noqa: F401
        except ImportError:
            return False, "textblob not installed (pip install textblob)"
        return True, "ok"
