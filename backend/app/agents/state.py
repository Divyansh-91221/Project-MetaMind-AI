"""Agent state.

An explicit state object (rather than hidden conversation state) makes the pipeline
inspectable, testable and easy to port to LangGraph later: each stage is a pure-ish function
from state to state.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.core.constants import CopilotIntent
from app.schemas.copilot import ChatMessage, EvidenceItem, ResolvedEntity, ToolCallTrace


@dataclass(slots=True)
class ToolPlanStep:
    """One planned tool invocation."""

    tool: str
    arguments: dict[str, object] = field(default_factory=dict)
    reason: str = ""


@dataclass(slots=True)
class AgentState:
    """Carries everything the pipeline produces, stage by stage."""

    query: str
    conversation_id: uuid.UUID = field(default_factory=uuid.uuid4)
    history: list[ChatMessage] = field(default_factory=list)
    context_urn: str | None = None
    max_evidence: int = 20

    # Stage outputs
    intent: CopilotIntent = CopilotIntent.UNKNOWN
    intent_confidence: float = 0.0
    mentions: list[str] = field(default_factory=list)
    resolved_entities: list[ResolvedEntity] = field(default_factory=list)
    plan: list[ToolPlanStep] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)
    tool_calls: list[ToolCallTrace] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    answer: str = ""
    followups: list[str] = field(default_factory=list)

    @property
    def primary_entity(self) -> ResolvedEntity | None:
        return self.resolved_entities[0] if self.resolved_entities else None

    @property
    def primary_urn(self) -> str | None:
        entity = self.primary_entity
        return entity.urn if entity else None

    def add_evidence(self, items: list[EvidenceItem]) -> None:
        """Append evidence, de-duplicating on (title, urn) and respecting the budget."""
        seen = {(item.title, item.urn) for item in self.evidence}
        for item in items:
            key = (item.title, item.urn)
            if key in seen or len(self.evidence) >= self.max_evidence:
                continue
            seen.add(key)
            self.evidence.append(item)

    def add_warnings(self, warnings: list[str]) -> None:
        for warning in warnings:
            if warning and warning not in self.warnings:
                self.warnings.append(warning)

    @property
    def has_inferred_evidence(self) -> bool:
        return any(item.inferred for item in self.evidence)
