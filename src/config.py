"""Environment-driven configuration (.env aware) shared by every component."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

VALID_ENGINES = ("vader", "textblob", "huggingface", "comprehend")
VALID_STORAGE_BACKENDS = ("sqlite", "dynamodb")
VALID_OBJECT_STORE_MODES = ("local", "s3")


@dataclass(frozen=True)
class Settings:
    # Sentiment engine
    sentiment_engine: str = "vader"
    neutral_threshold: float = 0.15
    hf_model: str = "distilbert-base-uncased-finetuned-sst-2-english"
    hf_api_url: str = "https://api-inference.huggingface.co/models"
    hf_token: str = ""
    request_timeout_s: int = 20

    # Storage
    storage_backend: str = "sqlite"
    sqlite_path: str = str(PROJECT_ROOT / "data" / "reviews.db")
    dynamodb_table: str = "reviews"
    dynamodb_endpoint_url: str | None = None
    aws_region: str = "us-east-1"

    # Object store used by the S3-event ingestion handler
    object_store_mode: str = "local"
    local_object_store_root: str = str(PROJECT_ROOT / "data")
    allow_local_path_ingest: bool = True

    # Limits / logging
    max_reviews_per_batch: int = 200
    log_level: str = "INFO"
    log_dir: str = str(PROJECT_ROOT / "logs")

    extras: dict = field(default_factory=dict, compare=False)

    def validate(self) -> None:
        from .errors import ReviewValidationError

        if self.sentiment_engine not in VALID_ENGINES:
            raise ReviewValidationError(
                f"SENTIMENT_ENGINE must be one of {VALID_ENGINES}, got {self.sentiment_engine!r}"
            )
        if self.storage_backend not in VALID_STORAGE_BACKENDS:
            raise ReviewValidationError(
                f"STORAGE_BACKEND must be one of {VALID_STORAGE_BACKENDS}, got {self.storage_backend!r}"
            )
        if self.object_store_mode not in VALID_OBJECT_STORE_MODES:
            raise ReviewValidationError(
                f"OBJECT_STORE_MODE must be one of {VALID_OBJECT_STORE_MODES}, got {self.object_store_mode!r}"
            )
        if not 0.0 <= self.neutral_threshold <= 1.0:
            raise ReviewValidationError("NEUTRAL_THRESHOLD must be between 0 and 1")


def _bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _abspath(raw: str) -> str:
    """Resolve relative paths against the project root (independent of cwd)."""
    path = Path(raw)
    return str(path if path.is_absolute() else PROJECT_ROOT / path)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Build Settings from environment variables (process-wide singleton)."""
    settings = Settings(
        sentiment_engine=os.getenv("SENTIMENT_ENGINE", "vader").strip().lower(),
        neutral_threshold=float(os.getenv("NEUTRAL_THRESHOLD", "0.15")),
        hf_model=os.getenv("HF_MODEL", "distilbert-base-uncased-finetuned-sst-2-english"),
        hf_api_url=os.getenv("HF_API_URL", "https://api-inference.huggingface.co/models").rstrip("/"),
        hf_token=os.getenv("HF_TOKEN", ""),
        request_timeout_s=int(os.getenv("REQUEST_TIMEOUT_S", "20")),
        storage_backend=os.getenv("STORAGE_BACKEND", "sqlite").strip().lower(),
        sqlite_path=_abspath(os.getenv("SQLITE_PATH", "data/reviews.db")),
        dynamodb_table=os.getenv("DYNAMODB_TABLE", "reviews"),
        dynamodb_endpoint_url=os.getenv("DYNAMODB_ENDPOINT_URL") or None,
        aws_region=os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1")),
        object_store_mode=os.getenv("OBJECT_STORE_MODE", "local").strip().lower(),
        local_object_store_root=_abspath(os.getenv("LOCAL_OBJECT_STORE_ROOT", "data")),
        allow_local_path_ingest=_bool(os.getenv("ALLOW_LOCAL_PATH_INGEST"), True),
        max_reviews_per_batch=int(os.getenv("MAX_REVIEWS", "200")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_dir=os.getenv("LOG_DIR", str(PROJECT_ROOT / "logs")),
    )
    settings.validate()
    return settings


def reset_settings_cache() -> None:
    """Testing hook: drop the cached Settings so env changes take effect."""
    get_settings.cache_clear()
