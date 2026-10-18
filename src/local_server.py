"""Local serverless mode: FastAPI app that forwards every request to lambda_handler.

The exact same handler functions deployed to AWS Lambda run here, so the whole
pipeline works on a Windows machine with no cloud credentials.
"""
from __future__ import annotations

import json
import time
import uuid

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import PROJECT_ROOT, get_settings
from .handlers import lambda_handler
from .logging_config import get_logger, setup_logging

settings = get_settings()
setup_logging(settings.log_level, settings.log_dir)
log = get_logger("local_server")

app = FastAPI(
    title="Customer Review Sentiment Pipeline (local mode)",
    description=f"Same handlers as the AWS Lambda deployment; storage={settings.storage_backend}, "
    f"engine={settings.sentiment_engine}",
    version="0.2.0",
)

_PASSTHROUGH_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def build_event(request: Request, raw_body: bytes) -> dict:
    """Wrap an incoming HTTP request as an API Gateway HTTP API (v2) event."""
    headers = {k.lower(): v for k, v in request.headers.items()}
    return {
        "version": "2.0",
        "rawPath": request.url.path,
        "rawQueryString": str(request.url.query),
        "headers": headers,
        "queryStringParameters": {k: v for k, v in request.query_params.multi_items()} or None,
        "requestContext": {
            "requestId": str(uuid.uuid4()),
            "http": {
                "method": request.method,
                "path": request.url.path,
                "sourceIp": request.client.host if request.client else "127.0.0.1",
            },
        },
        "body": raw_body.decode("utf-8", errors="replace") if raw_body else None,
        "isBase64Encoded": False,
    }


@app.middleware("http")
async def request_logger(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    log.info("%s %s -> %s (%.1f ms)", request.method, request.url.path, response.status_code, elapsed_ms)
    return response


@app.get("/", include_in_schema=False)
def root():
    return JSONResponse({
        "service": "review-sentiment-pipeline",
        "mode": "local (FastAPI -> lambda_handler)",
        "storage": settings.storage_backend,
        "engine": settings.sentiment_engine,
        "dashboard": "/ui/",
        "endpoints": {
            "GET /health": "storage + engine status",
            "GET /engines": "sentiment engine availability",
            "POST /reviews": "single review (JSON body)",
            "POST /ingest": "bulk CSV/JSON upload ({filename, content} or {path})",
            "POST /ingest/s3-event": "S3-style event bulk ingestion",
            "POST /process": "run sentiment + keywords over unprocessed reviews",
            "GET /summary": "overall stats (filters: sentiment, date_from, date_to, min_rating, max_rating, keyword, business_type)",
            "GET /reviews": "filtered list (same filters + limit, offset)",
            "GET /reviews/{id}": "single review by id",
            "GET /trends?period=day|week|month": "sentiment trend over time",
            "GET /keywords?sentiment=...&top_n=...": "top keywords",
        },
        "docs": "/docs",
    })


@app.api_route("/ingest/s3-event", methods=["POST"])
async def s3_event_endpoint(request: Request):
    """Accepts an S3 notification event JSON; runs the real S3-event handler."""
    raw = await request.body()
    try:
        event = json.loads(raw)
    except json.JSONDecodeError as exc:
        return JSONResponse(status_code=400, content={"error": "validation_error", "message": f"invalid JSON: {exc}"})
    result = lambda_handler(event, None)
    return Response(content=result["body"], status_code=result["statusCode"],
                    media_type=result.get("headers", {}).get("Content-Type", "application/json"))


# Static dashboard (registered before the catch-all so /ui/* is served, not proxied)
_DASHBOARD_DIR = PROJECT_ROOT / "dashboard"
if _DASHBOARD_DIR.is_dir():
    app.mount("/ui", StaticFiles(directory=str(_DASHBOARD_DIR), html=True), name="dashboard")


@app.api_route("/{path:path}", methods=sorted(_PASSTHROUGH_METHODS))
async def passthrough(path: str, request: Request):
    """Forward every other request to the Lambda handler and return its response."""
    raw = await request.body()
    event = build_event(request, raw)
    result = lambda_handler(event, None)
    return Response(
        content=result["body"],
        status_code=result["statusCode"],
        media_type=result.get("headers", {}).get("Content-Type", "application/json"),
    )
