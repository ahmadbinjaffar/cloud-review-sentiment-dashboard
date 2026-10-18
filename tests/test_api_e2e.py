"""End-to-end test: HTTP -> FastAPI -> lambda_handler -> storage -> response.

Covers the full journey a dashboard user takes: upload reviews, process them,
query every read endpoint, switch engines, and hit the error paths.
"""
from __future__ import annotations

import json

import pytest

REVIEWS = [
    {"text": "Absolutely wonderful, best pasta in town!", "rating": 5, "date": "2024-05-01", "business_type": "restaurant"},
    {"text": "Terrible service and a filthy floor, never again.", "rating": 1, "date": "2024-05-02", "business_type": "restaurant"},
    {"text": "The soup was okay, nothing special.", "rating": 3, "date": "2024-05-03", "business_type": "restaurant"},
]

CSV_UPLOAD = (
    "date,rating,text\n"
    "2024-06-01,5,Lovely staff and perfect coffee!\n"
    "2024-06-02,1,Cold food and rude waiters\n"
)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from src.local_server import app

    with TestClient(app) as test_client:
        yield test_client


def test_full_pipeline_journey(client):
    # 1. service is up and the dashboard is served
    assert client.get("/health").json()["status"] == "ok"
    assert "ReviewPulse" in client.get("/ui/").text
    assert client.get("/").json()["mode"].startswith("local")

    # 2. store three single reviews (each gets an id back)
    ids = []
    for review in REVIEWS:
        response = client.post("/reviews", json=review)
        assert response.status_code == 201
        ids.append(response.json()["review"]["review_id"])

    # 3. classify them with the default engine
    processed = client.post("/process", json={"review_ids": ids, "engine": "vader"}).json()["summary"]
    assert processed["processed"] == 3 and processed["failed"] == 0
    assert sum(processed["label_counts"].values()) == 3

    # 4. summary reflects the processed corpus
    summary = client.get("/summary").json()["summary"]
    assert summary["total_reviews"] == 3
    assert summary["processed_reviews"] == 3
    assert summary["avg_rating"] == 3.0
    assert summary["date_range"] == {"from": "2024-05-01", "to": "2024-05-03"}

    # 5. every read endpoint answers
    assert client.get("/reviews").json()["total_matches"] == 3
    assert client.get("/reviews").status_code == 200
    single = client.get(f"/reviews/{ids[0]}")
    assert single.status_code == 200 and single.json()["review"]["sentiment"] is not None
    trends = client.get("/trends", params={"period": "day"}).json()
    assert trends["total_reviews"] == 3 and len(trends["trends"]) == 3
    kws = client.get("/keywords", params={"sentiment": "positive", "top_n": 5}).json()
    assert isinstance(kws["keywords"], list)
    engines = {e["name"]: e["available"] for e in client.get("/engines").json()["engines"]}
    assert engines["vader"] is True

    # 6. CSV upload through the dashboard path
    uploaded = client.post("/ingest", json={"filename": "june.csv", "content": CSV_UPLOAD}).json()
    assert uploaded["valid_records"] == 2 and uploaded["stored"]["inserted"] == 2
    assert client.get("/summary").json()["summary"]["total_reviews"] == 5

    # 7. classify the upload too, then filter by sentiment
    assert client.post("/process", json={"limit": 10}).json()["summary"]["processed"] == 2
    positive = client.get("/reviews", params={"sentiment": "positive"}).json()
    negative = client.get("/reviews", params={"sentiment": "negative"}).json()
    assert positive["total_matches"] >= 1 and negative["total_matches"] >= 1
    assert positive["total_matches"] + negative["total_matches"] <= 5

    # 8. engine switching on a re-process
    reprocessed = client.post("/process", json={"review_ids": ids, "engine": "textblob"}).json()["summary"]
    assert reprocessed["engine"] == "textblob" and reprocessed["processed"] == 3
    assert client.get(f"/reviews/{ids[0]}").json()["review"]["engine"] == "textblob"


def test_error_paths_end_to_end(client):
    # validation errors
    assert client.post("/reviews", content="{oops",
                       headers={"Content-Type": "application/json"}).status_code == 400
    assert client.post("/reviews", json={"text": "x", "rating": 3, "date": "2024-05-01"}).status_code == 400
    assert client.get("/reviews", params={"sentiment": "angry"}).status_code == 400
    assert client.get("/trends", params={"period": "hour"}).status_code == 400

    # not-found errors
    assert client.get("/reviews/no-such-id").status_code == 404
    assert client.post("/process", json={"review_ids": ["ghost"]}).status_code == 404
    assert client.get("/definitely-missing").status_code == 404

    # unavailable engine
    missing_engine = client.post("/process", json={"engine": "does-not-exist"})
    assert missing_engine.status_code == 503
    assert missing_engine.json()["error"] == "engine_unavailable"

    # error bodies are structured JSON
    body = client.post("/reviews", json={"text": "x", "rating": 99, "date": "2024-05-01"}).json()
    assert body["error"] == "validation_error" and body["message"]


def test_dashboard_uploads_and_ui_assets(client):
    html = client.get("/ui/")
    assert html.status_code == 200 and html.headers["content-type"].startswith("text/html")
    for asset in ("/ui/css/styles.css", "/ui/js/app.js", "/ui/vendor/chart.umd.min.js"):
        assert client.get(asset).status_code == 200, asset


def test_ingest_s3_event_round_trip(client, temp_pipeline):
    """S3-style bulk upload through the local FastAPI route."""
    bucket_dir = temp_pipeline / "objects" / "events-bucket"
    bucket_dir.mkdir(parents=True)
    (bucket_dir / "batch.json").write_text(
        json.dumps([{"text": "Great ambience and lovely dessert", "rating": 5, "date": "2024-07-01"}]),
        encoding="utf-8",
    )
    event = {"Records": [{"s3": {"bucket": {"name": "events-bucket"}, "object": {"key": "batch.json"}}}]}
    response = client.post("/ingest/s3-event", json=event)
    assert response.status_code == 200
    assert response.json()["ingested"][0]["parsed"] == 1
    assert client.get("/summary").json()["summary"]["total_reviews"] == 1
