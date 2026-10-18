"""Aggregations used by the API handlers (summary, trends, keywords)."""
from __future__ import annotations

from collections import Counter, defaultdict

from .keywords import keyword_document_counts

SENTIMENTS = ("positive", "negative", "neutral")


def _subset(rows: list[dict], sentiment: str | None = None) -> list[dict]:
    if not sentiment:
        return rows
    return [r for r in rows if r.get("sentiment") == sentiment]


def summarize(rows: list[dict]) -> dict:
    """Overall stats: sentiment mix, ratings, business types, date range, confidence."""
    total = len(rows)
    processed = [r for r in rows if r.get("sentiment")]
    sentiment_counts = Counter(r["sentiment"] for r in processed)
    rating_counts = Counter(int(r["rating"]) for r in rows)
    by_type: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        by_type[r.get("business_type") or "unknown"][r.get("sentiment") or "unprocessed"] += 1
    dates = sorted(r["date"] for r in rows if r.get("date"))
    confidences = [float(r["confidence"]) for r in processed if r.get("confidence") is not None]
    return {
        "total_reviews": total,
        "processed_reviews": len(processed),
        "unprocessed_reviews": total - len(processed),
        "sentiment_counts": {s: sentiment_counts.get(s, 0) for s in SENTIMENTS},
        "sentiment_share": {
            s: round(sentiment_counts.get(s, 0) / len(processed), 4) for s in SENTIMENTS
        }
        if processed
        else {s: 0.0 for s in SENTIMENTS},
        "rating_distribution": {str(k): rating_counts.get(k, 0) for k in range(1, 6)},
        "avg_rating": round(sum(int(r["rating"]) for r in rows) / total, 3) if total else None,
        "avg_confidence": round(sum(confidences) / len(confidences), 4) if confidences else None,
        "by_business_type": {k: dict(v) for k, v in sorted(by_type.items())},
        "date_range": {"from": dates[0], "to": dates[-1]} if dates else None,
    }


def trends(rows: list[dict], period: str = "day") -> list[dict]:
    """Sentiment trend over time, grouped by day or month."""
    if period not in ("day", "month", "week"):
        raise ValueError("period must be day, week or month")
    buckets: dict[str, dict] = {}
    for r in sorted(rows, key=lambda x: x["date"]):
        key = r["date"][:7] if period == "month" else _iso_week(r["date"]) if period == "week" else r["date"][:10]
        b = buckets.setdefault(
            key,
            {"period": key, "total": 0, "positive": 0, "negative": 0, "neutral": 0, "unprocessed": 0, "rating_sum": 0},
        )
        b["total"] += 1
        b["rating_sum"] += int(r["rating"])
        b[r.get("sentiment") or "unprocessed"] += 1
    out = []
    for b in buckets.values():
        processed = b["positive"] + b["negative"] + b["neutral"]
        b["avg_rating"] = round(b.pop("rating_sum") / b["total"], 3)
        b["positive_rate"] = round(b["positive"] / processed, 4) if processed else None
        out.append(b)
    return out


def _iso_week(date_iso: str) -> str:
    from datetime import date

    d = date.fromisoformat(date_iso[:10])
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


def top_keywords(rows: list[dict], sentiment: str | None = None, top_n: int = 10) -> list[dict]:
    """Most frequent keywords (document frequency) in the review subset."""
    subset = _subset(rows, sentiment)
    keywords_per_review = []
    for r in subset:
        kws = r.get("keywords")
        if isinstance(kws, str):
            import json

            kws = json.loads(kws)
        if kws:
            keywords_per_review.append(list(kws))
    counts = keyword_document_counts(keywords_per_review)
    return [
        {"keyword": kw, "reviews": n, "share": round(n / len(subset), 4) if subset else 0.0}
        for kw, n in counts.most_common(top_n)
    ]
