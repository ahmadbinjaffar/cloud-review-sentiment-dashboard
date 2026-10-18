"""Pydantic models: review input validation and query filters."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .errors import ReviewValidationError

_SENTIMENTS = ("positive", "negative", "neutral")
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%Y/%m/%d")


def normalize_date(value: Any) -> str:
    """Accept several date formats, return ISO YYYY-MM-DD string."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raw = str(value).strip()
    if not raw:
        raise ValueError("empty date")
    try:
        return date.fromisoformat(raw[:10]).isoformat()
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date format: {value!r}")


class ReviewIn(BaseModel):
    """One customer review as accepted by ingestion."""

    text: str = Field(..., min_length=2, max_length=8000)
    rating: int = Field(..., ge=1, le=5)
    date: str
    business_name: str | None = None
    business_type: str | None = None
    source: str = "unknown"

    @field_validator("date")
    @classmethod
    def _check_date(cls, v: Any) -> str:
        return normalize_date(v)

    @field_validator("text")
    @classmethod
    def _check_text(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 2:
            raise ValueError("text is too short")
        return cleaned

    @field_validator("business_type", "business_name")
    @classmethod
    def _lower(cls, v: str | None) -> str | None:
        return v.strip().lower() if isinstance(v, str) and v.strip() else None


class ReviewFilters(BaseModel):
    """Filters accepted by the list / summary / trends / keywords endpoints."""

    sentiment: Literal["positive", "negative", "neutral"] | None = None
    date_from: str | None = None
    date_to: str | None = None
    min_rating: int | None = Field(default=None, ge=1, le=5)
    max_rating: int | None = Field(default=None, ge=1, le=5)
    keyword: str | None = None
    business_type: str | None = None
    processed_only: bool = False
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)

    @field_validator("date_from", "date_to")
    @classmethod
    def _check_date(cls, v: str | None) -> str | None:
        return normalize_date(v) if v else None

    @field_validator("sentiment", mode="before")
    @classmethod
    def _check_sentiment(cls, v: str | None) -> str | None:
        if v is None:
            return None
        lowered = str(v).lower()
        if lowered not in _SENTIMENTS:
            raise ValueError(f"sentiment must be one of {_SENTIMENTS}")
        return lowered

    @field_validator("keyword", "business_type")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return v.strip().lower() if v and v.strip() else None


def parse_review(payload: dict) -> dict:
    """Validate a raw dict into a review record, or raise ReviewValidationError."""
    try:
        return ReviewIn(**payload).model_dump()
    except Exception as exc:  # pydantic ValidationError or date errors
        raise ReviewValidationError(str(exc)) from exc


def parse_filters(params: dict) -> dict:
    """Validate query-string parameters into filter values, or raise."""
    try:
        return ReviewFilters(**params).model_dump()
    except Exception as exc:
        raise ReviewValidationError(str(exc)) from exc
