"""Hugging Face engine: local transformers model when installed, else Inference API.

Proposal names the Hugging Face Inference API (free tier) as the managed AI service;
offline it falls back to the same DistilBERT-SST2 model via `transformers` if present.
"""
from __future__ import annotations

from ..config import get_settings
from ..errors import EngineUnavailableError
from .base import SentimentEngine, SentimentResult

_NEGATIVE_LABELS = {"negative", "label_0", "neg"}
_POSITIVE_LABELS = {"positive", "label_1", "pos"}


class HuggingFaceEngine(SentimentEngine):
    name = "huggingface"

    def __init__(self):
        self._settings = get_settings()
        self._pipe = None
        if self._local_available()[0]:
            from transformers import pipeline

            self._pipe = pipeline(
                "sentiment-analysis",
                model=self._settings.hf_model,
                top_k=None,
                truncation=True,
            )

    # -- availability ------------------------------------------------------
    @staticmethod
    def _local_available() -> tuple[bool, str]:
        try:
            import transformers  # noqa: F401
        except ImportError:
            return False, "transformers not installed"
        return True, "ok"

    def _api_available(self) -> tuple[bool, str]:
        if not self._settings.hf_token:
            return False, "HF_TOKEN not set"
        return True, "ok"

    @classmethod
    def is_available(cls) -> tuple[bool, str]:
        local = cls._local_available()
        settings = get_settings()
        if local[0]:
            return True, f"local transformers model {settings.hf_model}"
        if settings.hf_token:
            return True, f"Hugging Face Inference API ({settings.hf_model})"
        return False, "no transformers install and no HF_TOKEN"

    # -- analysis ----------------------------------------------------------
    def analyze(self, text: str) -> SentimentResult:
        if self._pipe is not None:
            return self._analyze_local(text)
        return self._analyze_api(text)

    def _analyze_local(self, text: str) -> SentimentResult:
        raw = self._pipe(text[:1000])[0]
        probs = {str(item["label"]).lower(): float(item["score"]) for item in raw}
        return self._finalize(probs, mode="local-transformers")

    def _analyze_api(self, text: str) -> SentimentResult:
        import requests

        url = f"{self._settings.hf_api_url}/{self._settings.hf_model}"
        try:
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {self._settings.hf_token}"},
                json={"inputs": text[:1000]},
                timeout=self._settings.request_timeout_s,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise EngineUnavailableError(f"Hugging Face Inference API call failed: {exc}") from exc
        payload = response.json()
        if isinstance(payload, dict) and "error" in payload:
            raise EngineUnavailableError(f"Hugging Face API error: {payload['error']}")
        # API returns [[{label, score}, ...]] for a single input
        items = payload[0] if isinstance(payload, list) else payload
        probs = {str(item["label"]).lower(): float(item["score"]) for item in items}
        return self._finalize(probs, mode="inference-api")

    def _finalize(self, probs: dict[str, float], mode: str) -> SentimentResult:
        pos = next((v for k, v in probs.items() if k in _POSITIVE_LABELS or k.endswith("positive")), 0.0)
        neg = next((v for k, v in probs.items() if k in _NEGATIVE_LABELS or k.endswith("negative")), 0.0)
        total = pos + neg or 1.0
        p_pos, p_neg = pos / total, neg / total
        gap = abs(p_pos - p_neg)
        if gap < self._settings.neutral_threshold:
            label, confidence = "neutral", 1.0 - gap
        elif p_pos > p_neg:
            label, confidence = "positive", p_pos
        else:
            label, confidence = "negative", p_neg
        return SentimentResult(
            label=label,
            confidence=round(confidence, 4),
            scores={"positive": round(p_pos, 4), "negative": round(p_neg, 4), "raw": probs, "mode": mode},
            engine=self.name,
        )
