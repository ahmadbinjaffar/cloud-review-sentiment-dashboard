"""Storage interface (DynamoDB-style document store)."""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime


def new_review_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Storage(ABC):
    """Document store for reviews; both SQLite and DynamoDB implement this."""

    name: str = "base"

    @abstractmethod
    def insert_reviews(self, records: list[dict]) -> dict:
        """Bulk upsert by review_id; returns {'inserted': n, 'updated': n, 'skipped': n}."""

    @abstractmethod
    def get_review(self, review_id: str) -> dict | None:
        """Fetch one review by id."""

    @abstractmethod
    def update_sentiment(self, review_id: str, sentiment: str, confidence: float,
                         scores: dict, keywords: list[str], engine: str) -> bool:
        """Write sentiment result + keywords back onto the review record."""

    @abstractmethod
    def list_unprocessed(self, limit: int = 100) -> list[dict]:
        """Reviews with no sentiment yet (oldest first)."""

    @abstractmethod
    def query(self, filters: dict) -> list[dict]:
        """Filtered review list; filters from models.ReviewFilters."""

    @abstractmethod
    def count(self) -> int:
        """Total reviews stored."""

    @abstractmethod
    def ping(self) -> bool:
        """True when the backing store is reachable."""

    def close(self) -> None:  # optional for backends holding resources
        return None


def prepare_record(raw: dict, review_id: str | None = None) -> dict:
    """Fill id/timestamps on a validated review record."""
    record = dict(raw)
    record.setdefault("review_id", review_id or new_review_id())
    record.setdefault("created_at", utc_now())
    record.setdefault("source", "unknown")
    record.setdefault("sentiment", None)
    record.setdefault("confidence", None)
    record.setdefault("engine", None)
    record.setdefault("keywords", None)
    record.setdefault("processed_at", None)
    return record
