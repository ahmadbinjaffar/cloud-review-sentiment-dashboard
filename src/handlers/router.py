"""Single Lambda entry point routing API Gateway / S3 events to handlers.

Supports:
- S3 event notifications (Records[].s3) -> bulk ingestion
- API Gateway HTTP API (payload v2): routeKey "GET /summary", pathParameters {"id": ...}
- API Gateway REST API (payload v1): httpMethod + path
"""
from __future__ import annotations

import json

from ..config import get_settings
from ..errors import PipelineError
from ..logging_config import get_logger, setup_logging
from . import api, ingestion, processing

log = get_logger(__name__)

_ROUTES = {
    ("GET", "/health"): api.handle_health,
    ("GET", "/engines"): api.handle_engines,
    ("GET", "/summary"): api.handle_summary,
    ("GET", "/reviews"): api.handle_list_reviews,
    ("GET", "/trends"): api.handle_trends,
    ("GET", "/keywords"): api.handle_top_keywords,
    ("POST", "/reviews"): ingestion.handle_single_review,
    ("POST", "/ingest"): ingestion.handle_bulk_upload,
    ("POST", "/process"): processing.handle_process,
}


def _error_response(status: int, error_type: str, message: str) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": error_type, "message": message}),
    }


def _route(method: str, path: str):
    handler = _ROUTES.get((method, path))
    if handler is None and method == "GET" and path.startswith("/reviews/"):
        return api.handle_get_review
    return handler


def lambda_handler(event: dict, context=None) -> dict:
    """AWS Lambda-style entry point; also called by the local FastAPI server."""
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_dir)
    try:
        # S3 notification -> bulk ingestion
        records = event.get("Records")
        if records and isinstance(records, list) and "s3" in (records[0] or {}):
            return ingestion.handle_s3_event(event, context)

        # API Gateway HTTP API (v2) or REST API (v1) payload
        http = event.get("requestContext", {}).get("http", {})
        method = (http.get("method") or event.get("httpMethod") or "GET").upper()
        path = event.get("rawPath") or event.get("path") or "/"
        path = "/" + path.strip("/")

        handler = _route(method, path)
        if handler is None:
            return _error_response(404, "route_not_found", f"No route for {method} {path}")
        # Path-parameter fallback: /reviews/{id} without explicit pathParameters
        if handler is api.handle_get_review and not event.get("pathParameters"):
            event = {**event, "pathParameters": {"id": path.rsplit("/", 1)[-1]}}
        return handler(event, context)
    except PipelineError as exc:
        log.warning("Pipeline error on %s %s: %s", event.get("httpMethod", "event"), event.get("path", ""), exc)
        return _error_response(exc.status_code, exc.error_type, str(exc))
    except Exception as exc:
        log.exception("Unhandled error while serving event")
        return _error_response(500, "internal_error", f"Unhandled error: {exc}")
