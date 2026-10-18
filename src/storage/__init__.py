"""Storage factory: backend chosen by STORAGE_BACKEND config."""
from __future__ import annotations

from functools import lru_cache

from ..config import get_settings
from ..errors import StorageError
from .base import Storage
from .sqlite_store import SQLiteStorage

try:  # boto3 is optional until dynamodb backend is requested
    from .dynamodb_store import DynamoDBStorage
except StorageError:  # pragma: no cover - only when boto3 missing
    DynamoDBStorage = None  # type: ignore[assignment]


@lru_cache(maxsize=1)
def get_storage() -> Storage:
    """Return the configured, process-wide storage backend."""
    settings = get_settings()
    if settings.storage_backend == "sqlite":
        return SQLiteStorage(settings.sqlite_path)
    if settings.storage_backend == "dynamodb":
        if DynamoDBStorage is None:
            raise StorageError("STORAGE_BACKEND=dynamodb but boto3 is not installed")
        return DynamoDBStorage()
    raise StorageError(f"Unknown STORAGE_BACKEND {settings.storage_backend!r}")


def reset_storage_cache() -> None:
    """Testing hook: close and drop the cached backend."""
    from ..logging_config import get_logger

    try:
        get_storage().close()
    except Exception as exc:  # closing is best-effort  # noqa: BLE001
        get_logger(__name__).debug("Storage close during cache reset failed: %s", exc)
    get_storage.cache_clear()


__all__ = ["DynamoDBStorage", "SQLiteStorage", "Storage", "get_storage", "reset_storage_cache"]
