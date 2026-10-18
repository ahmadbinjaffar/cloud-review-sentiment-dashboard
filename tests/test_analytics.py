"""Unit tests for the aggregation functions behind the read APIs."""
from __future__ import annotations

import pytest

from src.analytics import summarize, top_keywords, trends


def _rows():
    return [
        {"date": "2024-05-01", "rating": 5, "sentiment": "positive", "confidence": 0.9,
         "business_type": "restaurant", "keywords": ["pizza", "nice"]},
        {"date": "2024-05-01", "rating": 1, "sentiment": "negative", "confidence": 0.8,
         "business_type": "cafe", "keywords": ["slow"]},
        {"date": "2024-06-02", "rating": 3, "sentiment": "neutral", "confidence": 0.6,
         "business_type": "restaurant", "keywords": ["pizza"]},
        {"date": "2024-06-03", "rating": 4, "sentiment": None, "confidence": None,
         "business_type": None, "keywords": None},
    ]


# ---------------------------------------------------------------- summarize
def test_summarize_counts_and_shares():
    stats = summarize(_rows())
    assert stats["total_reviews"] == 4
    assert stats["processed_reviews"] == 3
    assert stats["unprocessed_reviews"] == 1
    assert stats["sentiment_counts"] == {"positive": 1, "negative": 1, "neutral": 1}
    assert stats["sentiment_share"] == {"positive": round(1 / 3, 4), "negative": round(1 / 3, 4),
                                        "neutral": round(1 / 3, 4)}
    assert stats["rating_distribution"] == {"1": 1, "2": 0, "3": 1, "4": 1, "5": 1}
    assert stats["avg_rating"] == 3.25
    assert stats["date_range"] == {"from": "2024-05-01", "to": "2024-06-03"}


def test_summarize_groups_unknown_business_type():
    stats = summarize(_rows())
    assert "unknown" in stats["by_business_type"]
    assert stats["by_business_type"]["restaurant"]["positive"] == 1


def test_summarize_empty_rows_is_safe():
    stats = summarize([])
    assert stats["total_reviews"] == 0
    assert stats["avg_rating"] is None
    assert stats["sentiment_share"] == {"positive": 0.0, "negative": 0.0, "neutral": 0.0}
    assert stats["date_range"] is None


# ---------------------------------------------------------------- trends
def test_trends_by_month_aggregates_days():
    series = trends(_rows(), period="month")
    assert [b["period"] for b in series] == ["2024-05", "2024-06"]
    may = series[0]
    assert may["total"] == 2 and may["positive"] == 1 and may["negative"] == 1
    assert may["avg_rating"] == 3.0
    assert may["positive_rate"] == 0.5


def test_trends_by_day_and_positive_rate_none_when_unprocessed():
    series = trends([{"date": "2024-05-01", "rating": 3, "sentiment": None}], period="day")
    assert series[0]["period"] == "2024-05-01"
    assert series[0]["unprocessed"] == 1
    assert series[0]["positive_rate"] is None


def test_trends_rejects_bad_period():
    with pytest.raises(ValueError):
        trends(_rows(), period="hour")


# ---------------------------------------------------------------- keywords
def test_top_keywords_document_frequency_order():
    rows = top_keywords(_rows(), top_n=5)
    assert rows[0] == {"keyword": "pizza", "reviews": 2, "share": 0.5}


def test_top_keywords_filters_by_sentiment():
    rows = top_keywords(_rows(), sentiment="negative", top_n=5)
    assert [r["keyword"] for r in rows] == ["slow"]


def test_top_keywords_accepts_serialised_keyword_lists():
    rows = top_keywords([{"sentiment": "positive", "keywords": '["cozy", "cozy"]'}], sentiment="positive")
    assert rows[0]["keyword"] == "cozy" and rows[0]["reviews"] == 1
