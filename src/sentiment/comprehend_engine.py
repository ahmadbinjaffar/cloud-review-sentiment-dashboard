"""Amazon Comprehend adapter — only usable when AWS credentials exist."""
from __future__ import annotations

import os

from ..config import get_settings
from ..errors import EngineUnavailableError
from .base import SentimentEngine, SentimentResult


def _has_aws_credentials() -> bool:
    if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"):
        return True
    if os.getenv("AWS_PROFILE"):
        return True
    if os.getenv("AWS_WEB_IDENTITY_TOKEN_FILE") or os.getenv("AWS_ROLE_ARN"):
        return True
    shared = os.path.expanduser(r"~\.aws\credentials")
    return os.path.exists(shared)


class ComprehendEngine(SentimentEngine):
    name = "comprehend"

    def __init__(self):
        if not _has_aws_credentials():
            raise EngineUnavailableError(
                "Amazon Comprehend requires AWS credentials "
                "(AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY, AWS_PROFILE, or ~/.aws/credentials)"
            )
        import boto3

        settings = get_settings()
        self._client = boto3.client("comprehend", region_name=settings.aws_region)

    def analyze(self, text: str) -> SentimentResult:
        try:
            response = self._client.detect_sentiment(Text=text[:5000], LanguageCode="en")
        except Exception as exc:  # botocore ClientError family
            raise EngineUnavailableError(f"Amazon Comprehend call failed: {exc}") from exc
        label = str(response["Sentiment"]).lower()
        if label == "mixed":  # Comprehend-only label -> project's 3-class scheme
            label = "neutral"
        return SentimentResult(
            label=label,
            confidence=float(response["SentimentScore"].get(label.capitalize(), 0.0)),
            scores={k.lower(): float(v) for k, v in response["SentimentScore"].items()},
            engine=self.name,
        )

    @classmethod
    def is_available(cls) -> tuple[bool, str]:
        try:
            import boto3  # noqa: F401
        except ImportError:
            return False, "boto3 not installed (pip install boto3)"
        if not _has_aws_credentials():
            return False, "no AWS credentials found"
        return True, "AWS credentials present"
