"""Unit tests for the Lambda entry point (API Gateway + S3-style events)."""
from __future__ import annotations

import json

import pytest

from src.handlers import lambda_handler


def _get(path: str, params: dict | None = None) -> dict:
    return lambda_handler({"version": "2.0", "rawPath": path,
                           "requestContext": {"http": {"method": "GET"}},
                           "queryStringParameters": params or None}, None)


def _post(path: str, body) -> dict:
    event = {"version": "2.0", "rawPath": path,
             "requestContext": {"http": {"method": "POST"}},
             "body": body if isinstance(body, str) else json.dumps(body)}
    return lambda_handler(event, None)


def _body(response: dict) -> dict:
    return json.loads(response["body"])


# ---------------------------------------------------------------- routing
def test_health_route():
    response = _get("/health")
    assert response["statusCode"] == 200
    payload = _body(response)
    assert payload["status"] == "ok"
    assert payload["storage"] == {"backend": "sqlite", "reachable": True, "total_reviews": 0}
    assert payload["engine"] == "vader"


def test_engines_route_lists_four():
    payload = _body(_get("/engines"))
    assert len(payload["engines"]) == 4
    assert {e["name"] for e in payload["engines"]} == {"vader", "textblob", "huggingface", "comprehend"}


def test_unknown_route_returns_404():
    response = _get("/definitely-not-a-route")
    assert response["statusCode"] == 404
    assert _body(response)["error"] == "route_not_found"


def test_method_not_mapped_returns_404():
    response = lambda_handler({"rawPath": "/trends",
                               "requestContext": {"http": {"method": "DELETE"}}}, None)
    assert response["statusCode"] == 404


# ---------------------------------------------------------------- POST /reviews
def test_single_review_created_with_id():
    response = _post("/reviews", {"text": "Lovely staff and great coffee!", "rating": 5,
                                  "date": "2024-05-01", "business_type": "cafe"})
    assert response["statusCode"] == 201
    payload = _body(response)
    assert payload["stored"] == {"inserted": 1, "updated": 0, "skipped": 0}
    assert payload["review"]["review_id"]  # id is returned for chaining to /process
    assert payload["review"]["source"] == "api"


@pytest.mark.parametrize("body", ["{not json", json.dumps({"text": "ok text", "rating": 9, "date": "2024-05-01"})])
def test_single_review_validation_errors(body):
    response = _post("/reviews", body)
    assert response["statusCode"] == 400
    assert _body(response)["error"] == "validation_error"


def test_single_review_requires_json_object():
    response = _post("/reviews", json.dumps(["not", "an", "object"]))
    assert response["statusCode"] == 400


# ---------------------------------------------------------------- GET /reviews/{id}
def test_get_review_by_path_without_path_parameters():
    created = _body(_post("/reviews", {"text": "Fetch me by id please", "rating": 4,
                                       "date": "2024-05-01"}))
    rid = created["review"]["review_id"]
    response = lambda_handler({"rawPath": f"/reviews/{rid}",
                               "requestContext": {"http": {"method": "GET"}}}, None)
    assert response["statusCode"] == 200
    assert _body(response)["review"]["review_id"] == rid


def test_get_review_missing_id_404():
    response = lambda_handler({"rawPath": "/reviews/no-such-id",
                               "requestContext": {"http": {"method": "GET"}}}, None)
    assert response["statusCode"] == 404
    assert _body(response)["error"] == "not_found"


# ---------------------------------------------------------------- bulk ingest
def test_bulk_upload_csv_counts_rows():
    csv_content = (
        "date,rating,text\n"
        "2024-05-01,5,Great pasta!\n"
        "2024-05-02,1,Cold soup, terrible\n"
        "2024-05-03,9,rating out of range\n"
        "2024-05-01,5,Great pasta!\n"      # duplicate of row 1 within the file
    )
    response = _post("/ingest", {"filename": "reviews.csv", "content": csv_content})
    assert response["statusCode"] == 200
    payload = _body(response)
    assert payload["total_rows"] == 4
    assert payload["valid_records"] == 2  # 3 valid minus the in-file duplicate
    assert payload["duplicates_in_file"] == 1
    assert payload["invalid_rows"] == 1
    assert payload["stored"]["inserted"] == 2
    assert payload["invalid_samples"][0]["row"] == 3


def test_bulk_upload_rejects_missing_content():
    response = _post("/ingest", {"filename": "x.csv"})
    assert response["statusCode"] == 400


def test_bulk_upload_rejects_bad_json():
    response = _post("/ingest", "{oops")
    assert response["statusCode"] == 400


# ---------------------------------------------------------------- S3 event
def test_s3_event_ingests_from_local_object_store(temp_pipeline):
    bucket_dir = temp_pipeline / "objects" / "reviews-bucket" / "uploads"
    bucket_dir.mkdir(parents=True)
    (bucket_dir / "new.csv").write_text(
        "date,rating,text\n2024-05-01,5,Fantastic dinner!\n2024-05-02,2,Too noisy and crowded\n",
        encoding="utf-8",
    )
    event = {"Records": [{"s3": {"bucket": {"name": "reviews-bucket"},
                                 "object": {"key": "uploads/new.csv"}}}]}
    response = lambda_handler(event, None)
    assert response["statusCode"] == 200
    payload = _body(response)
    assert payload["ingested"][0]["parsed"] == 2
    assert payload["ingested"][0]["stored"]["inserted"] == 2


def test_s3_event_missing_object_404(temp_pipeline):
    event = {"Records": [{"s3": {"bucket": {"name": "reviews-bucket"},
                                 "object": {"key": "uploads/ghost.csv"}}}]}
    response = lambda_handler(event, None)
    assert response["statusCode"] == 404
    assert _body(response)["error"] == "object_not_found"


# ---------------------------------------------------------------- processing
def test_process_explicit_ids_end_to_end():
    created = _body(_post("/reviews", {"text": "Horrible queue, awful staff", "rating": 1,
                                       "date": "2024-05-01"}))
    rid = created["review"]["review_id"]
    response = _post("/process", {"review_ids": [rid], "engine": "vader"})
    assert response["statusCode"] == 200
    summary = _body(response)["summary"]
    assert summary["engine"] == "vader"
    assert summary["processed"] == 1 and summary["failed"] == 0
    assert summary["label_counts"]["negative"] == 1

    fetched = _body(_get(f"/reviews/{rid}"))["review"]
    assert fetched["sentiment"] == "negative"
    assert fetched["confidence"] > 0
    assert fetched["engine"] == "vader"
    assert isinstance(fetched["keywords"], list) and fetched["keywords"]


def test_process_unknown_id_404():
    response = _post("/process", {"review_ids": ["ghost-id"]})
    assert response["statusCode"] == 404


def test_process_unknown_engine_503():
    response = _post("/process", {"engine": "no-such-engine"})
    assert response["statusCode"] == 503
    assert _body(response)["error"] == "engine_unavailable"


def test_process_rejects_bad_limit_and_body():
    assert _post("/process", {"limit": 0})["statusCode"] == 400
    assert _post("/process", {"limit": "abc"})["statusCode"] == 400
    assert _post("/process", "{oops")["statusCode"] == 400
    assert _post("/process", {"limit": ""})["statusCode"] == 200  # empty -> default batch


# ---------------------------------------------------------------- read APIs
def test_summary_and_list_with_filters():
    _post("/reviews", {"text": "Amazing pasta and friendly waiter", "rating": 5, "date": "2024-05-01"})
    _post("/reviews", {"text": "Rude staff, dirty floor", "rating": 1, "date": "2024-05-02"})
    _post("/process", {"engine": "vader"})

    summary = _body(_get("/summary"))
    assert summary["summary"]["total_reviews"] == 2
    assert summary["summary"]["processed_reviews"] == 2
    assert summary["filters_applied"] == {}

    filtered = _body(_get("/summary", {"sentiment": "positive"}))
    assert filtered["summary"]["total_reviews"] == 1
    assert filtered["filters_applied"] == {"sentiment": "positive"}

    page = _body(_get("/reviews", {"limit": "1", "offset": "1"}))
    assert page["total_matches"] == 2 and page["returned"] == 1 and page["offset"] == 1


def test_trends_and_keywords_routes():
    _post("/reviews", {"text": "Wonderful meal overall", "rating": 5, "date": "2024-05-01"})
    _post("/process", {"engine": "vader"})

    trends = _body(_get("/trends", {"period": "month"}))
    assert trends["period"] == "month" and trends["trends"][0]["total"] == 1

    kws = _body(_get("/keywords", {"sentiment": "positive", "top_n": "3"}))
    assert kws["sentiment"] == "positive"
    assert 1 <= len(kws["keywords"]) <= 3

    grouped = _body(_get("/keywords"))
    assert set(grouped["by_sentiment"]) == {"positive", "negative", "neutral"}


@pytest.mark.parametrize("params", [{"period": "hour"}, {"top_n": "0"}, {"top_n": "many"},
                                    {"sentiment": "angry"}, {"limit": "99999"}])
def test_read_api_validation_errors(params):
    if "top_n" in params:
        response = _get("/keywords", params)
    elif "period" in params:
        response = _get("/trends", params)
    else:
        response = _get("/reviews", params)
    assert response["statusCode"] == 400
    assert _body(response)["error"] == "validation_error"
