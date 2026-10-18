"""Unit tests for input validation: dates, reviews, query filters."""
from __future__ import annotations

from datetime import date, datetime

import pytest

from src.errors import ReviewValidationError
from src.models import ReviewFilters, normalize_date, parse_filters, parse_review


# ---------------------------------------------------------------- dates
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2024-05-01", "2024-05-01"),
        ("01/05/2024", "2024-05-01"),
        ("05/01/2024", "2024-01-05"),  # day-first format matches before month-first
        ("May 1, 2024", "2024-05-01"),
        ("2024-5-1", "2024-05-01"),
        (date(2024, 5, 1), "2024-05-01"),
        (datetime(2024, 5, 1, 13, 45), "2024-05-01"),
    ],
)
def test_normalize_date_accepts_common_formats(raw, expected):
    assert normalize_date(raw) == expected


@pytest.mark.parametrize("raw", ["", "not a date", "31/02/2024"])
def test_normalize_date_rejects_garbage(raw):
    with pytest.raises(ValueError):
        normalize_date(raw)


# ---------------------------------------------------------------- review record
def test_parse_review_valid_record():
    record = parse_review(
        {"text": "  Nice place!  ", "rating": 4, "date": "01/05/2024", "business_type": " Restaurant "}
    )
    assert record["text"] == "Nice place!"
    assert record["date"] == "2024-05-01"
    assert record["business_type"] == "restaurant"


@pytest.mark.parametrize(
    "payload",
    [
        {"text": "ok text", "rating": 9, "date": "2024-05-01"},      # rating out of range
        {"text": "ok text", "rating": 0, "date": "2024-05-01"},      # rating out of range
        {"text": "x", "rating": 3, "date": "2024-05-01"},            # text too short
        {"rating": 3, "date": "2024-05-01"},                         # missing text
        {"text": "ok text", "rating": 3},                            # missing date
        {"text": "ok text", "rating": 3, "date": "someday"},         # bad date
    ],
)
def test_parse_review_rejects_invalid(payload):
    with pytest.raises(ReviewValidationError):
        parse_review(payload)


# ---------------------------------------------------------------- filters
def test_parse_filters_defaults_and_stripping():
    filters = parse_filters({"keyword": "  Pizza ", "business_type": " Restaurant "})
    assert filters["keyword"] == "pizza"
    assert filters["business_type"] == "restaurant"
    assert filters["limit"] == 100 and filters["offset"] == 0


def test_parse_filters_is_case_insensitive_on_sentiment():
    assert parse_filters({"sentiment": "POSITIVE"})["sentiment"] == "positive"
    assert parse_filters({"sentiment": "Negative"})["sentiment"] == "negative"


def test_parse_filters_rejects_bad_values():
    for bad in ({"sentiment": "happy"}, {"limit": "0"}, {"limit": "5000"},
                {"min_rating": "9"}, {"offset": "-1"}, {"date_from": "nope"}):
        with pytest.raises(ReviewValidationError):
            parse_filters(bad)


def test_review_filters_model_direct():
    model = ReviewFilters(sentiment="neutral", limit=5)
    assert model.sentiment == "neutral" and model.limit == 5
