"""Unit tests for the sentiment engine interface and the offline engines."""
from __future__ import annotations

import pytest

from src.errors import EngineUnavailableError
from src.sentiment import ENGINES, engine_status, get_engine
from src.sentiment.base import SentimentEngine, SentimentResult
from src.sentiment.comprehend_engine import ComprehendEngine
from src.sentiment.huggingface_engine import HuggingFaceEngine
from src.sentiment.textblob_engine import TextBlobEngine
from src.sentiment.vader_engine import VaderEngine

POSITIVE = "The food was absolutely wonderful, best meal ever!"
NEGATIVE = "Terrible service, cold food and a filthy table. Never again."
NEUTRAL = "The meeting is on Monday."


# ---------------------------------------------------------------- factory
def test_factory_returns_vader_by_default():
    engine = get_engine()
    assert engine.name == "vader"


def test_factory_unknown_engine_raises():
    with pytest.raises(EngineUnavailableError) as exc:
        get_engine("does-not-exist")
    assert "does-not-exist" in str(exc.value)


def test_engine_status_lists_all_engines():
    status = engine_status()
    assert {s["name"] for s in status} == set(ENGINES)
    vader = next(s for s in status if s["name"] == "vader")
    assert vader["available"] is True


def test_comprehend_unavailable_without_aws_creds():
    available, reason = ComprehendEngine.is_available()
    if available:
        pytest.skip("AWS credentials present on this machine")
    assert not available and reason
    with pytest.raises(EngineUnavailableError):
        get_engine("comprehend")


def test_huggingface_availability_is_a_typed_tuple():
    available, reason = HuggingFaceEngine.is_available()
    assert isinstance(available, bool) and isinstance(reason, str) and reason
    if not available:
        with pytest.raises(EngineUnavailableError):
            get_engine("huggingface")


# ---------------------------------------------------------------- 3-class rule
def test_label_from_binary_mapping():
    rule = SentimentEngine.label_from_binary
    assert rule(0.8, 0.1, 0.15) == "positive"
    assert rule(0.1, 0.8, 0.15) == "negative"
    assert rule(0.5, 0.5, 0.15) == "neutral"


def test_label_from_binary_exact_boundary_is_neutral():
    # gap equal to the threshold is NOT beyond it -> neutral (>= / > rule)
    assert SentimentEngine.label_from_binary(0.6, 0.4, 0.2) == "neutral"


def test_sentiment_result_as_dict_is_rounded():
    result = SentimentResult(label="positive", confidence=0.123456, scores={"positive": 0.987654}, engine="vader")
    payload = result.as_dict()
    assert payload == {"sentiment": "positive", "confidence": 0.1235, "scores": {"positive": 0.9877}, "engine": "vader"}


# ---------------------------------------------------------------- VADER
def test_vader_positive_negative_neutral():
    engine = VaderEngine()
    assert engine.analyze(POSITIVE).label == "positive"
    assert engine.analyze(NEGATIVE).label == "negative"
    assert engine.analyze(NEUTRAL).label == "neutral"


def test_vader_confidence_and_scores_in_range():
    result = VaderEngine().analyze(POSITIVE)
    assert 0.0 <= result.confidence <= 1.0
    assert set(result.scores) == {"positive", "negative", "neutral", "compound"}
    assert abs(sum(result.scores[k] for k in ("positive", "negative", "neutral")) - 1.0) < 1e-6


def test_vader_neutral_threshold_widens_neutral_band():
    wide = VaderEngine(neutral_threshold=0.99)
    assert wide.analyze(POSITIVE).label == "neutral"  # compound 0.87 < 0.99
    default = VaderEngine(neutral_threshold=0.15)
    assert default.analyze(POSITIVE).label == "positive"


def test_vader_is_available():
    assert VaderEngine.is_available() == (True, "ok")


# ---------------------------------------------------------------- TextBlob
def test_textblob_positive_negative_neutral():
    engine = TextBlobEngine()
    assert engine.analyze("Absolutely wonderful, I loved it!").label == "positive"
    assert engine.analyze("Horrible, worst experience ever.").label == "negative"
    assert engine.analyze("The table is in the room.").label == "neutral"


def test_textblob_threshold_moves_polarity_into_neutral():
    engine = TextBlobEngine(neutral_threshold=0.99)
    result = engine.analyze("Absolutely wonderful, I loved it!")  # polarity ~0.94
    assert result.label == "neutral"
    assert 0.0 <= result.confidence <= 1.0
