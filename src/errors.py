"""Custom exceptions for the review pipeline."""


class PipelineError(Exception):
    """Base class for all pipeline errors."""

    status_code = 500
    error_type = "internal_error"


class ReviewValidationError(PipelineError):
    """Bad input data (missing fields, wrong types, out-of-range values)."""

    status_code = 400
    error_type = "validation_error"


class ReviewNotFoundError(PipelineError):
    """Requested review id does not exist."""

    status_code = 404
    error_type = "not_found"


class EngineUnavailableError(PipelineError):
    """The requested sentiment engine cannot run (missing package/credentials)."""

    status_code = 503
    error_type = "engine_unavailable"


class StorageError(PipelineError):
    """Database read/write failure."""

    status_code = 500
    error_type = "storage_error"


class ObjectNotFoundError(PipelineError):
    """Bulk-ingest source object (S3 key or local file) not found."""

    status_code = 404
    error_type = "object_not_found"
