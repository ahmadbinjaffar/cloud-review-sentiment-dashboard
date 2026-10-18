"""Unit tests for the SQLite storage backend (the local DynamoDB-style store)."""
from __future__ import annotations

from src.storage.base import prepare_record


# ---------------------------------------------------------------- insert / get
def test_insert_and_count(seeded_storage):
    assert seeded_storage.count() == 3
    assert seeded_storage.ping() is True
    assert seeded_storage.name == "sqlite"


def test_get_review_returns_record_or_none(seeded_storage):
    rows = seeded_storage.query({})
    record = seeded_storage.get_review(rows[0]["review_id"])
    assert record["text"] == rows[0]["text"]
    assert record["sentiment"] is None  # not processed yet
    assert seeded_storage.get_review("missing-id") is None


def test_prepare_record_fills_defaults():
    record = prepare_record({"text": "hi there", "rating": 3, "date": "2024-05-01", "source": "t"})
    assert record["sentiment"] is None and record["processed_at"] is None
    assert record["review_id"] and record["created_at"]


# ---------------------------------------------------------------- upsert semantics
def test_reingest_unprocessed_record_updates_in_place(seeded_storage):
    rows = seeded_storage.query({})
    rid = rows[0]["review_id"]
    stats = seeded_storage.insert_reviews([{**rows[0], "text": "updated text here"}])
    assert stats == {"inserted": 0, "updated": 1, "skipped": 0}
    assert seeded_storage.get_review(rid)["text"] == "updated text here"
    assert seeded_storage.count() == 3  # no duplicate row


def test_reingest_processed_record_is_skipped(seeded_storage):
    rows = seeded_storage.query({})
    rid = rows[0]["review_id"]
    seeded_storage.update_sentiment(rid, "positive", 0.9, {"positive": 0.9}, ["pizza"], "vader")
    stats = seeded_storage.insert_reviews([{**rows[0], "text": "changed"}])
    assert stats == {"inserted": 0, "updated": 0, "skipped": 1}
    kept = seeded_storage.get_review(rid)
    assert kept["text"] == rows[0]["text"] and kept["sentiment"] == "positive"


# ---------------------------------------------------------------- sentiment write-back
def test_update_sentiment_writes_all_fields(seeded_storage):
    rows = seeded_storage.query({})
    rid = rows[0]["review_id"]
    assert seeded_storage.update_sentiment(rid, "negative", 0.75, {"negative": 0.75}, ["slow"], "vader") is True
    record = seeded_storage.get_review(rid)
    assert record["sentiment"] == "negative"
    assert record["confidence"] == 0.75
    assert record["scores"] == {"negative": 0.75}
    assert record["keywords"] == ["slow"]
    assert record["engine"] == "vader"
    assert record["processed_at"]


def test_update_sentiment_unknown_id_returns_false(seeded_storage):
    assert seeded_storage.update_sentiment("nope", "positive", 0.9, {}, [], "vader") is False


# ---------------------------------------------------------------- unprocessed + query
def test_list_unprocessed_excludes_processed_and_respects_limit(seeded_storage):
    rows = seeded_storage.query({})
    seeded_storage.update_sentiment(rows[0]["review_id"], "positive", 0.9, {}, [], "vader")
    pending = seeded_storage.list_unprocessed()
    assert len(pending) == 2
    assert all(r["sentiment"] is None for r in pending)
    assert len(seeded_storage.list_unprocessed(limit=1)) == 1


def test_query_filters(seeded_storage, sample_records):
    storage = seeded_storage
    rows = storage.query({})
    storage.update_sentiment(rows[0]["review_id"], "positive", 0.9, {}, [], "vader")

    assert len(storage.query({"sentiment": "positive"})) == 1
    assert len(storage.query({"sentiment": "negative"})) == 0
    assert len(storage.query({"date_from": "2024-05-02"})) == 2
    assert len(storage.query({"date_to": "2024-05-01"})) == 1
    assert len(storage.query({"min_rating": 3})) == 2
    assert len(storage.query({"max_rating": 1})) == 1
    assert len(storage.query({"business_type": "restaurant"})) == 3
    assert len(storage.query({"keyword": "wonderful"})) == 1
    assert len(storage.query({"processed_only": True})) == 1
    assert len(storage.query({"min_rating": 4, "max_rating": 5})) == 1
    assert len(storage.query({"date_from": "2024-01-01", "date_to": "2024-12-31",
                              "business_type": "cafe"})) == 0
