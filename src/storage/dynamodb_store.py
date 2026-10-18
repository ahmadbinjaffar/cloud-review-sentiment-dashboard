"""DynamoDB implementation of the Storage interface (cloud mode).

Selected with STORAGE_BACKEND=dynamodb. Works against real AWS or a local
DynamoDB endpoint via DYNAMODB_ENDPOINT_URL. Requires AWS credentials.
"""
from __future__ import annotations

import json

from ..config import get_settings
from ..errors import StorageError
from ..logging_config import get_logger
from .base import Storage, prepare_record, utc_now

_KEY = "review_id"


class DynamoDBStorage(Storage):
    name = "dynamodb"

    def __init__(self, table: str | None = None, endpoint_url: str | None = None, region: str | None = None):
        settings = get_settings()
        try:
            import boto3
        except ImportError as exc:
            raise StorageError("boto3 is required for STORAGE_BACKEND=dynamodb (pip install boto3)") from exc
        resource_kwargs = {"region_name": region or settings.aws_region}
        resolved_endpoint = endpoint_url or settings.dynamodb_endpoint_url
        if resolved_endpoint:
            resource_kwargs["endpoint_url"] = resolved_endpoint
        self._dynamodb = boto3.resource("dynamodb", **resource_kwargs)
        self._table_name = table or settings.dynamodb_table
        self._table = self._ensure_table()

    def _ensure_table(self):
        log = get_logger(__name__)
        try:
            self._dynamodb.meta.client.describe_table(TableName=self._table_name)
            return self._dynamodb.Table(self._table_name)
        except Exception as exc:  # table missing -> try to create it  # noqa: BLE001
            log.debug("describe_table(%s) failed, attempting create: %s", self._table_name, exc)
        try:
            table = self._dynamodb.create_table(
                TableName=self._table_name,
                KeySchema=[{"AttributeName": _KEY, "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": _KEY, "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
            )
            table.wait_until_exists()
            return table
        except Exception as exc:
            raise StorageError(f"Cannot create/access DynamoDB table {self._table_name!r}: {exc}") from exc

    # -- writes -------------------------------------------------------------
    def insert_reviews(self, records: list[dict]) -> dict:
        inserted = updated = skipped = 0

        try:
            for raw in records:
                rec = prepare_record(raw)
                existing = self.get_review(rec[_KEY])
                if existing is None:
                    self._table.put_item(Item=self._to_item(rec))
                    inserted += 1
                elif existing.get("sentiment"):
                    skipped += 1
                else:
                    self._table.update_item(
                        Key={_KEY: rec[_KEY]},
                        UpdateExpression="SET #t=:t, #d=:d, #r=:r, bn=:bn, bt=:bt, src=:src",
                        ExpressionAttributeNames={"#t": "text", "#d": "date", "#r": "rating",
                                                   "bn": "business_name", "bt": "business_type", "src": "source"},
                        ExpressionAttributeValues={":t": rec["text"], ":d": rec["date"], ":r": rec["rating"],
                                                    ":bn": rec.get("business_name"), ":bt": rec.get("business_type"),
                                                    ":src": rec.get("source", "unknown")},
                    )
                    updated += 1
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(f"DynamoDB insert failed: {exc}") from exc
        return {"inserted": inserted, "updated": updated, "skipped": skipped}

    def update_sentiment(self, review_id: str, sentiment: str, confidence: float,
                         scores: dict, keywords: list[str], engine: str) -> bool:
        try:
            self._table.update_item(
                Key={_KEY: review_id},
                UpdateExpression="SET sentiment=:s, confidence=:c, scores=:sc, keywords=:k, engine=:e, processed_at=:p",
                ExpressionAttributeValues={
                    ":s": sentiment, ":c": round(float(confidence), 4),
                    ":sc": json.dumps(scores), ":k": list(keywords), ":e": engine, ":p": utc_now(),
                },
            )
            return True
        except Exception as exc:
            raise StorageError(f"DynamoDB update failed: {exc}") from exc

    # -- reads --------------------------------------------------------------
    def get_review(self, review_id: str) -> dict | None:
        try:
            response = self._table.get_item(Key={_KEY: review_id})
        except Exception as exc:
            raise StorageError(f"DynamoDB get_item failed: {exc}") from exc
        item = response.get("Item")
        return self._from_item(item) if item else None

    def list_unprocessed(self, limit: int = 100) -> list[dict]:
        from boto3.dynamodb.conditions import Attr

        try:
            response = self._table.scan(
                FilterExpression=Attr("sentiment").not_exists(),
                Limit=limit,
            )
        except Exception as exc:
            raise StorageError(f"DynamoDB scan failed: {exc}") from exc
        items = sorted(response.get("Items", []), key=lambda i: (i.get("date", ""), i.get("created_at", "")))
        return [self._from_item(i) for i in items[:limit]]

    def query(self, filters: dict) -> list[dict]:
        from boto3.dynamodb.conditions import Attr

        expressions = []
        if filters.get("sentiment"):
            expressions.append(Attr("sentiment").eq(filters["sentiment"]))
        if filters.get("business_type"):
            expressions.append(Attr("business_type").eq(filters["business_type"]))
        if filters.get("min_rating") is not None:
            expressions.append(Attr("rating").gte(filters["min_rating"]))
        if filters.get("max_rating") is not None:
            expressions.append(Attr("rating").lte(filters["max_rating"]))
        if filters.get("date_from"):
            expressions.append(Attr("date").gte(filters["date_from"]))
        if filters.get("date_to"):
            expressions.append(Attr("date").lte(filters["date_to"]))
        if filters.get("processed_only"):
            expressions.append(Attr("sentiment").exists())

        kwargs = {}
        if expressions:
            expr = expressions[0]
            for extra in expressions[1:]:
                expr = expr & extra
            kwargs["FilterExpression"] = expr
        items = []
        try:
            paginator = self._dynamodb.meta.client.get_paginator("scan")
            for page in paginator.paginate(TableName=self._table_name, **kwargs):
                items.extend(page.get("Items", []))
        except Exception as exc:
            raise StorageError(f"DynamoDB scan failed: {exc}") from exc
        records = sorted((self._from_item(i) for i in items), key=lambda r: (r["date"], r[_KEY]))
        keyword = filters.get("keyword")
        if keyword:
            records = [r for r in records if keyword in r["text"].lower()]
        return records

    def count(self) -> int:
        try:
            return int(self._table.item_count)
        except Exception as exc:
            raise StorageError(f"DynamoDB count failed: {exc}") from exc

    def ping(self) -> bool:
        try:
            self._dynamodb.meta.client.describe_table(TableName=self._table_name)
            return True
        except Exception as exc:  # any AWS error -> report unreachable  # noqa: BLE001
            get_logger(__name__).debug("DynamoDB ping failed: %s", exc)
            return False

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _to_item(rec: dict) -> dict:
        item = {c: rec.get(c) for c in
                ("review_id", "text", "date", "rating", "business_name", "business_type",
                 "source", "sentiment", "confidence", "engine", "created_at", "processed_at")}
        item["scores"] = json.dumps(rec.get("scores") or {})
        item["keywords"] = list(rec.get("keywords") or []) or None
        return {k: v for k, v in item.items() if v is not None}

    @staticmethod
    def _from_item(item: dict) -> dict:
        rec = dict(item)
        scores = rec.get("scores")
        rec["scores"] = json.loads(scores) if isinstance(scores, str) else (scores or {})
        kws = rec.get("keywords")
        rec["keywords"] = list(kws) if kws else None
        rec.setdefault("business_name", None)
        rec.setdefault("business_type", None)
        rec.setdefault("sentiment", None)
        rec.setdefault("confidence", None)
        rec.setdefault("engine", None)
        rec.setdefault("processed_at", None)
        rec["rating"] = int(rec.get("rating", 0))
        return rec
