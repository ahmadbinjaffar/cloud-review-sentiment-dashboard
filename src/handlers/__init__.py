"""Handler package: ingestion, processing, read-only API, and the Lambda router."""
from .router import lambda_handler

__all__ = ["lambda_handler"]
