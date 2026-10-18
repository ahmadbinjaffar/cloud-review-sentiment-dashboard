"""Lambda-style handlers for review ingestion (bulk S3 event + single + upload)."""
from __future__ import annotations

import base64
import csv
import io
import json
from pathlib import Path
from urllib.parse import unquote_plus

from ..config import get_settings
from ..errors import ObjectNotFoundError, ReviewValidationError
from ..logging_config import get_logger, setup_logging
from ..models import parse_review
from ..storage import get_storage
from ..storage.base import new_review_id

log = get_logger(__name__)

REQUIRED_COLUMNS = {"date", "rating", "text"}
COLUMN_ALIASES = {
    "review date": "date", "review_date": "date", "posted": "date",
    "review text": "text", "review": "text", "review body": "text", "content": "text",
    "stars": "rating", "score": "rating",
    "business": "business_name", "business name": "business_name", "name": "business_name",
    "category": "business_type", "type": "business_type",
}


# --------------------------------------------------------------------------
# Parsing / validation helpers
# --------------------------------------------------------------------------
def _normalise_columns(row: dict) -> dict:
    normalised = {}
    for key, value in row.items():
        lowered = str(key).strip().lower()
        normalised[COLUMN_ALIASES.get(lowered, lowered)] = value
    return normalised


def parse_records(content: str, filename: str = "upload.csv", source: str = "upload") -> dict:
    """Parse CSV / JSON / JSONL content into validated review records.

    Returns {'records': [...], 'invalid': [{'row': n, 'error': str}], 'total': n}.
    """
    name = filename.lower()
    raw_rows: list[dict] = []
    if name.endswith(".json"):
        payload = json.loads(content)
        raw_rows = payload.get("reviews", payload) if isinstance(payload, dict) else payload
        if not isinstance(raw_rows, list):
            raise ReviewValidationError("JSON upload must be a list of reviews or {'reviews': [...]}")
    elif name.endswith((".jsonl", ".ndjson")):
        raw_rows = [json.loads(line) for line in content.splitlines() if line.strip()]
    else:  # CSV (default)
        reader = csv.DictReader(io.StringIO(content))
        if reader.fieldnames is None:
            raise ReviewValidationError("CSV upload has no header row")
        raw_rows = list(reader)

    records, invalid = [], []
    seen_ids: set[str] = set()
    for idx, raw in enumerate(raw_rows, start=1):
        if not isinstance(raw, dict):
            invalid.append({"row": idx, "error": "not an object"})
            continue
        row = _normalise_columns(raw)
        if not any(str(v or "").strip() for v in row.values()):
            continue  # fully empty row: skip silently
        try:
            record = parse_review(row)
        except ReviewValidationError as exc:
            invalid.append({"row": idx, "error": str(exc).split("\n")[0][:200]})
            continue
        record["source"] = str(raw.get("source") or source).strip().lower()
        rid = str(raw.get("review_id") or "").strip()
        if rid:
            if rid in seen_ids:
                invalid.append({"row": idx, "error": f"duplicate review_id {rid}"})
                continue
            seen_ids.add(rid)
            record["review_id"] = rid
        records.append(record)

    # duplicate text+date rows within the same file
    deduped, seen_keys, dupes = [], set(), 0
    for rec in records:
        key = (rec["date"], rec["text"].strip().lower())
        if key in seen_keys:
            dupes += 1
            continue
        seen_keys.add(key)
        deduped.append(rec)
    return {"records": deduped, "invalid": invalid, "duplicates": dupes, "total": len(raw_rows)}


# --------------------------------------------------------------------------
# Object fetching (S3 or local file, selected by config)
# --------------------------------------------------------------------------
class S3ObjectFetcher:
    def __init__(self):
        import boto3

        settings = get_settings()
        self._s3 = boto3.client("s3", region_name=settings.aws_region)

    def get(self, bucket: str, key: str) -> bytes:
        try:
            response = self._s3.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()
        except Exception as exc:
            raise ObjectNotFoundError(f"s3://{bucket}/{key} could not be read: {exc}") from exc


class localObjectFetcher:
    """Reads objects from a local directory — simulates S3 for offline runs.

    Layout: <root>/<bucket>/<key>; if the bucket subdirectory does not exist the
    file is read flat from <root>/<key> (single-bucket local layout).
    """

    def __init__(self, root: str):
        self._root = Path(root)

    def get(self, bucket: str, key: str) -> bytes:
        for path in (self._root / bucket / key, self._root / key):
            if path.is_file():
                return path.read_bytes()
        raise ObjectNotFoundError(
            f"Local object store: {key!r} not found under {self._root} (bucket {bucket!r})"
        )


def get_object_fetcher():
    settings = get_settings()
    if settings.object_store_mode == "s3":
        return S3ObjectFetcher()
    return localObjectFetcher(settings.local_object_store_root)


# --------------------------------------------------------------------------
# Lambda handlers
# --------------------------------------------------------------------------
def handle_s3_event(event: dict, context=None) -> dict:
    """Bulk ingestion triggered by S3 (or an S3-style event in local mode)."""
    setup_logging(get_settings().log_level, get_settings().log_dir)
    storage = get_storage()
    fetcher = get_object_fetcher()
    records = event.get("Records") or []
    if not records:
        raise ReviewValidationError("Event contains no Records")

    results = []
    for record in records:
        s3info = record.get("s3") or {}
        bucket = (s3info.get("bucket") or {}).get("name")
        key = unquote_plus((s3info.get("object") or {}).get("key", ""))
        if not bucket or not key:
            raise ReviewValidationError("Each record must contain s3.bucket.name and s3.object.key")
        content = fetcher.get(bucket, key).decode("utf-8-sig", errors="replace")
        source = f"s3://{bucket}/{key}"
        parsed = parse_records(content, filename=key, source=source)
        stored = storage.insert_reviews(parsed["records"])
        log.info("Ingested %s: %s records, %s invalid, stored=%s", source, len(parsed["records"]),
                 len(parsed["invalid"]), stored)
        results.append({"source": source, "parsed": len(parsed["records"]),
                        "duplicates_in_file": parsed["duplicates"], "invalid_rows": len(parsed["invalid"]),
                        "stored": stored, "invalid_samples": parsed["invalid"][:5]})
    return {"statusCode": 200, "body": json.dumps({"ingested": results})}


def handle_single_review(event: dict, context=None) -> dict:
    """POST /reviews — validate and store one review."""
    setup_logging(get_settings().log_level, get_settings().log_dir)
    body = event.get("body") or ""
    if isinstance(body, str):
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError as exc:
            raise ReviewValidationError(f"Request body is not valid JSON: {exc}") from exc
    else:
        payload = body
    if not isinstance(payload, dict):
        raise ReviewValidationError("Request body must be a JSON object")
    payload.setdefault("source", "api")
    record = parse_review(payload)
    record.setdefault("review_id", new_review_id())  # id known to the caller before insert
    stored = get_storage().insert_reviews([record])
    log.info("Single review stored: %s (id=%s)", stored, record["review_id"])
    return {"statusCode": 201, "body": json.dumps({"stored": stored, "review": record})}


def handle_bulk_upload(event: dict, context=None) -> dict:
    """POST /ingest — CSV/JSON content inline, base64, or a local path (local mode)."""
    setup_logging(get_settings().log_level, get_settings().log_dir)
    settings = get_settings()
    body = event.get("body") or ""
    if isinstance(body, str):
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError as exc:
            raise ReviewValidationError(f"Request body is not valid JSON: {exc}") from exc
    else:
        payload = body
    if not isinstance(payload, dict):
        raise ReviewValidationError("Body must be JSON: {filename, content[, encoding] | path}")

    if "path" in payload:
        if not settings.allow_local_path_ingest:
            raise ReviewValidationError("Local path ingestion is disabled (ALLOW_LOCAL_PATH_INGEST=false)")
        path = Path(payload["path"])
        if not path.is_absolute():
            path = Path(settings.local_object_store_root).parent / path
        if not path.is_file():
            raise ObjectNotFoundError(f"File not found: {path}")
        content = path.read_text(encoding="utf-8-sig", errors="replace")
        filename = payload.get("filename") or path.name
    elif "content" in payload:
        content = payload["content"]
        if payload.get("encoding", "").lower() == "base64":
            content = base64.b64decode(content).decode("utf-8-sig", errors="replace")
        filename = payload.get("filename", "upload.csv")
    else:
        raise ReviewValidationError("Body must contain either 'content' or 'path'")

    parsed = parse_records(content, filename=filename, source=f"upload:{filename}")
    stored = get_storage().insert_reviews(parsed["records"])
    log.info("Bulk upload %s: parsed=%s invalid=%s stored=%s", filename,
             len(parsed["records"]), len(parsed["invalid"]), stored)
    return {
        "statusCode": 200,
        "body": json.dumps({
            "file": filename, "total_rows": parsed["total"],
            "valid_records": len(parsed["records"]), "duplicates_in_file": parsed["duplicates"],
            "stored": stored, "invalid_rows": len(parsed["invalid"]),
            "invalid_samples": parsed["invalid"][:10],
        }),
    }
