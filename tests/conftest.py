"""Pytest fixtures: every test runs against a fresh temp SQLite DB and logs."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest


@pytest.fixture(autouse=True)
def temp_pipeline(tmp_path, monkeypatch):
    """Point config at temp storage/logs and reset process-wide caches."""
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "reviews.db"))
    monkeypatch.setenv("LOCAL_OBJECT_STORE_ROOT", str(tmp_path / "objects"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("SENTIMENT_ENGINE", "vader")
    monkeypatch.setenv("NEUTRAL_THRESHOLD", "0.15")
    monkeypatch.setenv("STORAGE_BACKEND", "sqlite")
    monkeypatch.delenv("HF_TOKEN", raising=False)

    from src.config import reset_settings_cache
    from src.storage import reset_storage_cache

    reset_settings_cache()
    reset_storage_cache()
    yield tmp_path
    reset_storage_cache()
    reset_settings_cache()


@pytest.fixture
def sample_records() -> list[dict]:
    """Three minimal reviews: positive, negative, neutral wording."""
    return [
        {"text": "Absolutely wonderful, I loved it!", "rating": 5, "date": "2024-05-01",
         "business_type": "restaurant", "source": "test"},
        {"text": "Terrible service, cold food. Never again.", "rating": 1, "date": "2024-05-02",
         "business_type": "restaurant", "source": "test"},
        {"text": "The table is in the room.", "rating": 3, "date": "2024-05-03",
         "business_type": "restaurant", "source": "test"},
    ]


@pytest.fixture
def seeded_storage(sample_records):
    """Storage instance with the sample records inserted."""
    from src.storage import get_storage

    storage = get_storage()
    storage.insert_reviews(sample_records)
    return storage
