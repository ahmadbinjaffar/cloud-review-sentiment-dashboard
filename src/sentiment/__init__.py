"""Engine factory + availability report."""
from __future__ import annotations

from ..config import get_settings
from ..errors import EngineUnavailableError
from .base import SentimentEngine, SentimentResult
from .comprehend_engine import ComprehendEngine
from .huggingface_engine import HuggingFaceEngine
from .textblob_engine import TextBlobEngine
from .vader_engine import VaderEngine

ENGINES: dict[str, type[SentimentEngine]] = {
    "vader": VaderEngine,
    "textblob": TextBlobEngine,
    "huggingface": HuggingFaceEngine,
    "comprehend": ComprehendEngine,
}


def get_engine(name: str | None = None) -> SentimentEngine:
    """Instantiate the requested engine (default: SENTIMENT_ENGINE from config)."""
    engine_name = (name or get_settings().sentiment_engine).strip().lower()
    engine_cls = ENGINES.get(engine_name)
    if engine_cls is None:
        raise EngineUnavailableError(f"Unknown engine {engine_name!r}; available: {sorted(ENGINES)}")
    available, reason = engine_cls.is_available()
    if not available:
        raise EngineUnavailableError(f"Engine {engine_name!r} unavailable: {reason}")
    return engine_cls()


def engine_status() -> list[dict]:
    """Availability of every registered engine (for diagnostics endpoints)."""
    return [
        {"name": name, "available": cls.is_available()[0], "detail": cls.is_available()[1]}
        for name, cls in ENGINES.items()
    ]


__all__ = ["ENGINES", "SentimentEngine", "SentimentResult", "engine_status", "get_engine"]
