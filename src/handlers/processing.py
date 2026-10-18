"""Processing handler: clean text -> sentiment -> keywords -> write back."""
from __future__ import annotations

import json
import time

from ..cleaning import clean_text
from ..config import get_settings
from ..errors import ReviewNotFoundError, ReviewValidationError
from ..keywords import extract_keywords
from ..logging_config import get_logger, setup_logging
from ..sentiment import get_engine
from ..storage import get_storage

log = get_logger(__name__)


def _process_one(storage, engine, review: dict) -> dict:
    cleaned = clean_text(review["text"])
    if not cleaned:
        raise ReviewValidationError(f"Review {review['review_id']} has no usable text after cleaning")
    result = engine.analyze(cleaned)
    keywords = extract_keywords(cleaned, top_n=8)
    storage.update_sentiment(
        review_id=review["review_id"],
        sentiment=result.label,
        confidence=result.confidence,
        scores=result.scores,
        keywords=keywords,
        engine=result.engine,
    )
    return {"review_id": review["review_id"], **result.as_dict(), "keywords": keywords}


def handle_process(event: dict, context=None) -> dict:
    """Classify unprocessed reviews (or explicit ids) and write results back.

    Event body (all optional): {"limit": int, "engine": str, "review_ids": [...]}
    """
    setup_logging(get_settings().log_level, get_settings().log_dir)
    settings = get_settings()
    body = event.get("body") or {}
    if isinstance(body, str) and body.strip():
        try:
            body = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ReviewValidationError(f"Request body is not valid JSON: {exc}") from exc
    if not isinstance(body, dict):
        raise ReviewValidationError("Body must be a JSON object")

    raw_limit = body.get("limit")
    if raw_limit in (None, ""):
        limit = settings.max_reviews_per_batch
    else:
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError) as exc:
            raise ReviewValidationError("limit must be an integer") from exc
    if limit < 1 or limit > 10000:
        raise ReviewValidationError("limit must be between 1 and 10000")
    engine = get_engine(body.get("engine"))
    storage = get_storage()

    review_ids = body.get("review_ids") or []
    if review_ids:
        targets = []
        for rid in review_ids:
            review = storage.get_review(str(rid))
            if review is None:
                raise ReviewNotFoundError(f"Review {rid!r} not found")
            targets.append(review)
    else:
        targets = storage.list_unprocessed(limit=limit)

    processed, failures = [], []
    started = time.time()
    for review in targets:
        try:
            outcome = _process_one(storage, engine, review)
            processed.append(outcome)
            log.info("Processed %s -> %s (%.2f)", outcome["review_id"], outcome["sentiment"], outcome["confidence"])
        except Exception as exc:  # one bad review must not kill the batch
            log.exception("Failed to process review %s", review.get("review_id"))
            failures.append({"review_id": review.get("review_id"), "error": str(exc)})

    summary = {
        "engine": engine.name,
        "requested": len(targets),
        "processed": len(processed),
        "failed": len(failures),
        "seconds": round(time.time() - started, 2),
        "label_counts": {
            label: sum(1 for r in processed if r["sentiment"] == label)
            for label in ("positive", "negative", "neutral")
        },
    }
    return {"statusCode": 200, "body": json.dumps({"summary": summary, "results": processed, "failures": failures})}
