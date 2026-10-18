"""SQLite implementation of the Storage interface (local mode, zero setup)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from ..errors import StorageError
from .base import Storage, prepare_record, utc_now

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
    review_id     TEXT PRIMARY KEY,
    text          TEXT NOT NULL,
    date          TEXT NOT NULL,
    rating        INTEGER NOT NULL,
    business_name TEXT,
    business_type TEXT,
    source        TEXT NOT NULL DEFAULT 'unknown',
    sentiment     TEXT,
    confidence    REAL,
    scores_json   TEXT,
    keywords_json TEXT,
    engine        TEXT,
    created_at    TEXT NOT NULL,
    processed_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_reviews_date ON reviews(date);
CREATE INDEX IF NOT EXISTS idx_reviews_rating ON reviews(rating);
CREATE INDEX IF NOT EXISTS idx_reviews_sentiment ON reviews(sentiment);
"""

_COLUMNS = ("review_id", "text", "date", "rating", "business_name", "business_type",
            "source", "sentiment", "confidence", "engine", "created_at", "processed_at")


class SQLiteStorage(Storage):
    name = "sqlite"

    def __init__(self, path: str):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # -- writes -------------------------------------------------------------
    def insert_reviews(self, records: list[dict]) -> dict:
        inserted = updated = skipped = 0
        try:
            for raw in records:
                rec = prepare_record(raw)
                existing = self.get_review(rec["review_id"])
                if existing is None:
                    self._conn.execute(
                        """INSERT INTO reviews (review_id, text, date, rating, business_name,
                           business_type, source, sentiment, confidence, scores_json,
                           keywords_json, engine, created_at, processed_at)
                           VALUES (:review_id, :text, :date, :rating, :business_name,
                           :business_type, :source, :sentiment, :confidence, :scores_json,
                           :keywords_json, :engine, :created_at, :processed_at)""",
                        self._row_out(rec),
                    )
                    inserted += 1
                elif existing.get("sentiment"):
                    skipped += 1  # already processed -> keep results (idempotent re-ingest)
                else:
                    self._conn.execute(
                        """UPDATE reviews SET text=:text, date=:date, rating=:rating,
                           business_name=:business_name, business_type=:business_type, source=:source
                           WHERE review_id=:review_id""",
                        self._row_out(rec),
                    )
                    updated += 1
            self._conn.commit()
        except sqlite3.Error as exc:
            self._conn.rollback()
            raise StorageError(f"SQLite insert failed: {exc}") from exc
        return {"inserted": inserted, "updated": updated, "skipped": skipped}

    def update_sentiment(self, review_id: str, sentiment: str, confidence: float,
                         scores: dict, keywords: list[str], engine: str) -> bool:
        try:
            cur = self._conn.execute(
                """UPDATE reviews SET sentiment=?, confidence=?, scores_json=?, keywords_json=?,
                   engine=?, processed_at=? WHERE review_id=?""",
                (sentiment, float(confidence), json.dumps(scores), json.dumps(keywords),
                 engine, utc_now(), review_id),
            )
            self._conn.commit()
            return cur.rowcount > 0
        except sqlite3.Error as exc:
            raise StorageError(f"SQLite update failed: {exc}") from exc

    # -- reads --------------------------------------------------------------
    def get_review(self, review_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM reviews WHERE review_id=?", (review_id,)
        ).fetchone()
        return self._row_in(row) if row else None

    def list_unprocessed(self, limit: int = 100) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM reviews WHERE sentiment IS NULL ORDER BY date, created_at LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_in(r) for r in rows]

    def query(self, filters: dict) -> list[dict]:
        sql, params = "SELECT * FROM reviews", []
        where = []
        if filters.get("sentiment"):
            where.append("sentiment = ?")
            params.append(filters["sentiment"])
        if filters.get("date_from"):
            where.append("date >= ?")
            params.append(filters["date_from"])
        if filters.get("date_to"):
            where.append("date <= ?")
            params.append(filters["date_to"])
        if filters.get("min_rating") is not None:
            where.append("rating >= ?")
            params.append(filters["min_rating"])
        if filters.get("max_rating") is not None:
            where.append("rating <= ?")
            params.append(filters["max_rating"])
        if filters.get("business_type"):
            where.append("business_type = ?")
            params.append(filters["business_type"])
        if filters.get("processed_only"):
            where.append("sentiment IS NOT NULL")
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY date, review_id"
        # keyword filter needs LIKE on text; applied in Python if LIKE would break index use
        rows = self._conn.execute(sql, params).fetchall()
        records = [self._row_in(r) for r in rows]
        keyword = filters.get("keyword")
        if keyword:
            records = [r for r in records if keyword in r["text"].lower()]
        return records

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0])

    def ping(self) -> bool:
        try:
            self._conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    def close(self) -> None:
        self._conn.close()

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _row_out(rec: dict) -> dict:
        row = {c: rec.get(c) for c in _COLUMNS}
        row["scores_json"] = json.dumps(rec.get("scores") or {})
        row["keywords_json"] = json.dumps(rec.get("keywords") or []) if rec.get("keywords") else None
        return row

    @staticmethod
    def _row_in(row: sqlite3.Row) -> dict:
        rec = {c: row[c] for c in _COLUMNS}
        rec["scores"] = json.loads(row["scores_json"] or "{}")
        rec["keywords"] = json.loads(row["keywords_json"]) if row["keywords_json"] else None
        return rec
