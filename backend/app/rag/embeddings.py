"""Embedding provider abstraction.

``EmbeddingProvider`` is the extension point; the default ``hash`` provider is fully offline
and deterministic so the platform runs with no API keys and tests stay reproducible.
Swapping in a hosted model is a configuration change, not a code change.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol, runtime_checkable

from app.core.config import settings
from app.core.exceptions import ProviderError
from app.core.logging import get_logger

logger = get_logger(__name__)

_TOKEN = re.compile(r"[a-z0-9_]+")


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Turns text into dense vectors."""

    name: str
    dimension: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_one(self, text: str) -> list[float]: ...


class HashEmbeddingProvider:
    """Deterministic bag-of-tokens hashing embedder.

    Not a semantic model - it captures lexical overlap only. It exists so the whole RAG and
    hybrid-search pipeline is exercisable offline; set ``EMBEDDING_PROVIDER=openai`` for real
    semantic retrieval.
    """

    name = "hash"

    def __init__(self, dimension: int | None = None) -> None:
        self.dimension = dimension or settings.embedding_dimension

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = _TOKEN.findall(text.lower())
        if not tokens:
            return vector

        for token in tokens:
            # Two hashes per token reduce collision artefacts in low-dimensional buckets.
            for salt in (b"", b"#"):
                digest = hashlib.blake2b(token.encode("utf-8") + salt, digest_size=8).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimension
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    async def embed_one(self, text: str) -> list[float]:
        return self._vector(text)


class OpenAIEmbeddingProvider:
    """Hosted embeddings via the OpenAI-compatible API."""

    name = "openai"

    def __init__(self) -> None:
        if not settings.embedding_api_key:
            raise ProviderError(
                "EMBEDDING_PROVIDER=openai requires EMBEDDING_API_KEY to be configured."
            )
        self.dimension = settings.embedding_dimension
        self.model = settings.embedding_model
        self._client = None

    def _get_client(self):  # type: ignore[no-untyped-def]
        if self._client is None:
            from openai import AsyncOpenAI

            assert settings.embedding_api_key is not None  # noqa: S101 - checked in __init__
            self._client = AsyncOpenAI(
                api_key=settings.embedding_api_key.get_secret_value(),
                base_url=settings.embedding_api_base or None,
            )
        return self._client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = await self._get_client().embeddings.create(model=self.model, input=texts)
        except Exception as exc:  # noqa: BLE001 - normalised into a domain error
            logger.error("embedding_request_failed", extra={"error": str(exc)})
            raise ProviderError("Embedding provider request failed.") from exc
        return [item.embedding for item in response.data]

    async def embed_one(self, text: str) -> list[float]:
        vectors = await self.embed([text])
        return vectors[0] if vectors else [0.0] * self.dimension


_provider: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    """Return the configured provider (cached for the process lifetime)."""
    global _provider  # noqa: PLW0603
    if _provider is None:
        _provider = (
            OpenAIEmbeddingProvider()
            if settings.embedding_provider == "openai"
            else HashEmbeddingProvider()
        )
        logger.info(
            "embedding_provider_selected",
            extra={"provider": _provider.name, "dimension": _provider.dimension},
        )
    return _provider


def set_embedding_provider(provider: EmbeddingProvider) -> None:
    """Override the provider (used by tests)."""
    global _provider  # noqa: PLW0603
    _provider = provider


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Cosine similarity clamped to ``[0, 1]`` for use as a score."""
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))
