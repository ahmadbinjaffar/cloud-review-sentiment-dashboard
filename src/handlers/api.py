"""Read-only API handlers: summary stats, review list, trends, top keywords."""
from __future__ import annotations

import json

from ..analytics import summarize, top_keywords, trends
from ..config import get_settings
from ..errors import ReviewNotFoundError, ReviewValidationError
from ..logging_config import get_logger, setup_logging
from ..models import parse_filters
from ..sentiment import engine_status
from ..storage import get_storage

log = get_logger(__name__)


def _ok(payload: dict, status: int = 200) -> dict:
    return {"statusCode": status, "headers": {"Content-Type": "application/json"}, "body": json.dumps(payload)}


def handle_health(event: dict, context=None) -> dict:
    """GET /health — storage reachability + active engine."""
    settings = get_settings()
    storage = get_storage()
    healthy = storage.ping()
    return _ok({
        "status": "ok" if healthy else "degraded",
        "storage": {"backend": storage.name, "reachable": healthy, "total_reviews": storage.count() if healthy else None},
        "engine": settings.sentiment_engine,
    })


def handle_engines(event: dict, context=None) -> dict:
    """GET /engines — availability of every sentiment engine."""
    return _ok({"engines": engine_status()})


def _filters_from_event(event: dict) -> dict:
    params = event.get("queryStringParameters") or {}
    return parse_filters({k: v for k, v in params.items() if v not in (None, "")})


def handle_summary(event: dict, context=None) -> dict:
    """GET /summary — overall sentiment/rating stats (supports the same filters)."""
    setup_logging(get_settings().log_level, get_settings().log_dir)
    filters = _filters_from_event(event)
    rows = get_storage().query(filters)
    applied = {k: v for k, v in filters.items() if v not in (None, False, 0)}
    applied.pop("limit", None)
    applied.pop("offset", None)
    return _ok({"filters_applied": applied, "summary": summarize(rows)})


def handle_list_reviews(event: dict, context=None) -> dict:
    """GET /reviews — filtered, paginated review list."""
    setup_logging(get_settings().log_level, get_settings().log_dir)
    filters = _filters_from_event(event)
    rows = get_storage().query(filters)
    page = rows[filters["offset"]: filters["offset"] + filters["limit"]]
    return _ok({
        "total_matches": len(rows),
        "limit": filters["limit"],
        "offset": filters["offset"],
        "returned": len(page),
        "reviews": page,
    })


def handle_trends(event: dict, context=None) -> dict:
    """GET /trends?period=day|week|month — sentiment trend over time."""
    setup_logging(get_settings().log_level, get_settings().log_dir)
    params = event.get("queryStringParameters") or {}
    period = (params.get("period") or "day").strip().lower()
    if period not in ("day", "week", "month"):
        raise ReviewValidationError("period must be day, week or month")
    filters = _filters_from_event(event)
    rows = get_storage().query(filters)
    series = trends(rows, period=period)
    log.info("Trends computed: period=%s buckets=%s", period, len(series))
    return _ok({"period": period, "total_reviews": len(rows), "trends": series})


def handle_top_keywords(event: dict, context=None) -> dict:
    """GET /keywords?sentiment=...&top_n=... — most frequent keywords."""
    setup_logging(get_settings().log_level, get_settings().log_dir)
    params = event.get("queryStringParameters") or {}
    raw_top = params.get("top_n")
    try:
        top_n = int(raw_top) if raw_top else 10
    except ValueError as exc:
        raise ReviewValidationError("top_n must be an integer") from exc
    if not 1 <= top_n <= 100:
        raise ReviewValidationError("top_n must be between 1 and 100")
    filters = _filters_from_event(event)
    rows = get_storage().query(filters)
    payload = {"sentiment": filters.get("sentiment"), "top_n": top_n}
    if filters.get("sentiment"):
        payload["keywords"] = top_keywords(rows, sentiment=filters["sentiment"], top_n=top_n)
    else:
        payload["by_sentiment"] = {
            s: top_keywords(rows, sentiment=s, top_n=top_n) for s in ("positive", "negative", "neutral")
        }
    return _ok(payload)


def handle_get_review(event: dict, context=None) -> dict:
    """GET /reviews/{id} — one review by id."""
    setup_logging(get_settings().log_level, get_settings().log_dir)
    review_id = (event.get("pathParameters") or {}).get("id") or ""
    if not review_id:
        raise ReviewValidationError("Missing review id in path")
    review = get_storage().get_review(review_id)
    if review is None:
        raise ReviewNotFoundError(f"Review {review_id!r} not found")
    return _ok({"review": review})
