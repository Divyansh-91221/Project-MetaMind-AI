"""Agent tool contract.

Tools are the *only* way the agent obtains facts. Each tool wraps a domain service, returns
typed :class:`EvidenceItem` records with URNs and sources, and is individually testable. The
LLM chooses between tools and verbalises their output - it never queries data itself.
"""

from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.schemas.copilot import EvidenceItem, ToolCallTrace

logger = get_logger(__name__)


@dataclass(slots=True)
class ToolResult:
    """Everything a tool returns: evidence for the answer, data for the UI, a short summary."""

    summary: str = ""
    evidence: list[EvidenceItem] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.evidence)


class Tool(abc.ABC):
    """Base class for Copilot tools."""

    name: str = "tool"
    description: str = ""
    argument_hint: str = ""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @abc.abstractmethod
    async def run(self, **kwargs: Any) -> ToolResult:
        """Execute the tool. Implementations must never raise for 'not found' cases."""

    async def invoke(self, **kwargs: Any) -> tuple[ToolResult, ToolCallTrace]:
        """Run the tool with timing, error capture and a trace record for observability."""
        started = time.perf_counter()
        try:
            result = await self.run(**kwargs)
            trace = ToolCallTrace(
                tool=self.name,
                arguments=_safe_arguments(kwargs),
                succeeded=True,
                result_count=result.count,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            return result, trace
        except Exception as exc:  # noqa: BLE001 - a failing tool degrades, never crashes
            logger.warning("tool_failed", extra={"tool": self.name, "error": str(exc)})
            trace = ToolCallTrace(
                tool=self.name,
                arguments=_safe_arguments(kwargs),
                succeeded=False,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                error=str(exc),
            )
            return ToolResult(warnings=[f"{self.name} failed: {exc}"]), trace

    def spec(self) -> dict[str, str]:
        """Description surfaced to the model when tool choice is delegated to the LLM."""
        return {"name": self.name, "description": self.description, "arguments": self.argument_hint}


def _safe_arguments(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Keep traces small and free of large payloads."""
    return {
        key: (value if isinstance(value, str | int | float | bool) else str(type(value).__name__))
        for key, value in kwargs.items()
    }
