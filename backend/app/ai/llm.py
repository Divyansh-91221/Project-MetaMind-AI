"""LLM provider abstraction.

The agent must never be coupled to a single vendor, so all model access goes through
``LLMProvider``. Three implementations ship:

``mock``          deterministic, offline; returns the evidence-grounded draft unchanged
``openai``        OpenAI-compatible chat completions with JSON-schema structured output
``azure_openai``  the same wire protocol against an Azure deployment

The mock provider is the default so a developer can run the entire Copilot without any API
key, and so tests are deterministic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from app.core.config import settings
from app.core.exceptions import ProviderError
from app.core.logging import get_logger
from app.utils.serialization import extract_json

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

DRAFT_PATTERN = re.compile(r"<draft>(?P<body>.*?)</draft>", re.DOTALL)


@dataclass(slots=True)
class LLMMessage:
    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(slots=True)
class LLMResponse:
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str = "stop"


@runtime_checkable
class LLMProvider(Protocol):
    """Vendor-neutral chat interface."""

    name: str
    model: str

    async def complete(
        self, messages: list[LLMMessage], *, temperature: float | None = None
    ) -> LLMResponse: ...

    async def structured(
        self, messages: list[LLMMessage], response_model: type[T]
    ) -> T | None: ...


class MockLLMProvider:
    """Offline provider.

    ``complete`` returns the ``<draft>`` block the agent already assembled from retrieved
    evidence, so answers stay factual with no model available. ``structured`` returns ``None``
    so callers fall back to their deterministic implementation.
    """

    name = "mock"

    def __init__(self, model: str = "mock-deterministic") -> None:
        self.model = model

    async def complete(
        self, messages: list[LLMMessage], *, temperature: float | None = None
    ) -> LLMResponse:
        last_user = next(
            (message.content for message in reversed(messages) if message.role == "user"), ""
        )
        match = DRAFT_PATTERN.search(last_user)
        content = match.group("body").strip() if match else last_user.strip()
        return LLMResponse(content=content, model=self.model, finish_reason="mock")

    async def structured(
        self, messages: list[LLMMessage], response_model: type[T]
    ) -> T | None:
        return None


class OpenAICompatibleProvider:
    """OpenAI / Azure OpenAI chat completions."""

    def __init__(self, *, azure: bool = False) -> None:
        if not settings.llm_api_key:
            raise ProviderError(
                f"LLM_PROVIDER={settings.llm_provider} requires LLM_API_KEY to be configured."
            )
        self.name = "azure_openai" if azure else "openai"
        self.model = settings.llm_model
        self._azure = azure
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            assert settings.llm_api_key is not None  # noqa: S101 - checked in __init__
            key = settings.llm_api_key.get_secret_value()
            if self._azure:
                from openai import AsyncAzureOpenAI

                if not settings.llm_api_base:
                    raise ProviderError("Azure OpenAI requires LLM_API_BASE.")
                self._client = AsyncAzureOpenAI(
                    api_key=key,
                    azure_endpoint=settings.llm_api_base,
                    api_version="2024-08-01-preview",
                    timeout=settings.llm_timeout_seconds,
                )
            else:
                from openai import AsyncOpenAI

                self._client = AsyncOpenAI(
                    api_key=key,
                    base_url=settings.llm_api_base or None,
                    timeout=settings.llm_timeout_seconds,
                )
        return self._client

    async def complete(
        self, messages: list[LLMMessage], *, temperature: float | None = None
    ) -> LLMResponse:
        try:
            response = await self._get_client().chat.completions.create(
                model=self.model,
                messages=[message.to_dict() for message in messages],
                temperature=(
                    settings.llm_temperature if temperature is None else temperature
                ),
                max_tokens=settings.llm_max_tokens,
            )
        except Exception as exc:  # noqa: BLE001 - normalised into a domain error
            logger.error("llm_request_failed", extra={"error": str(exc)})
            raise ProviderError("LLM request failed.") from exc

        choice = response.choices[0]
        usage = getattr(response, "usage", None)
        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            finish_reason=choice.finish_reason or "stop",
        )

    async def structured(
        self, messages: list[LLMMessage], response_model: type[T]
    ) -> T | None:
        """Request JSON matching the Pydantic model, tolerating providers without schema support."""
        schema_hint = LLMMessage(
            role="system",
            content=(
                "Respond with a single JSON object and nothing else. It must validate against "
                f"this JSON Schema:\n{response_model.model_json_schema()}"
            ),
        )
        try:
            response = await self.complete([schema_hint, *messages], temperature=0.0)
        except ProviderError:
            return None

        payload = extract_json(response.content)
        if payload is None:
            logger.warning("llm_structured_output_unparseable")
            return None
        try:
            return response_model.model_validate(payload)
        except Exception as exc:  # noqa: BLE001 - malformed output must not break the request
            logger.warning("llm_structured_output_invalid", extra={"error": str(exc)})
            return None


_provider: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    """Return the configured provider (cached for the process lifetime)."""
    global _provider  # noqa: PLW0603
    if _provider is None:
        if settings.llm_provider == "openai":
            _provider = OpenAICompatibleProvider(azure=False)
        elif settings.llm_provider == "azure_openai":
            _provider = OpenAICompatibleProvider(azure=True)
        else:
            _provider = MockLLMProvider()
        logger.info("llm_provider_selected", extra={"provider": _provider.name})
    return _provider


def set_llm_provider(provider: LLMProvider) -> None:
    """Override the provider (used by tests)."""
    global _provider  # noqa: PLW0603
    _provider = provider
