"""Copilot (AI agent) API contracts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.core.constants import CopilotIntent
from app.schemas.common import APIModel


class ChatMessage(APIModel):
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime | None = None


class EvidenceItem(APIModel):
    """A single traceable fact used to build the answer.

    Every claim in a Copilot response should map to at least one evidence item. This is what
    makes answers auditable and prevents the model from inventing lineage.
    """

    kind: Literal["entity", "lineage", "impact", "document", "glossary", "governance", "quality"]
    title: str
    detail: str = ""
    urn: str | None = None
    source: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    inferred: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)


class ToolCallTrace(APIModel):
    """Observability record of one tool invocation."""

    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    succeeded: bool = True
    result_count: int = 0
    duration_ms: float = 0.0
    error: str | None = None


class ResolvedEntity(APIModel):
    urn: str
    name: str
    qualified_name: str
    entity_type: str
    platform: str
    score: float = 0.0


class CopilotChatRequest(APIModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None
    history: list[ChatMessage] = Field(default_factory=list)
    entity_urn: str | None = Field(
        default=None, description="Optional page context, e.g. the asset the user is viewing."
    )
    max_evidence: int = Field(default=20, ge=1, le=100)


class CopilotChatResponse(APIModel):
    conversation_id: uuid.UUID
    answer: str
    intent: CopilotIntent = CopilotIntent.UNKNOWN
    resolved_entities: list[ResolvedEntity] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)
    suggested_followups: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    took_ms: float = 0.0


class IntentClassification(APIModel):
    """Structured output contract for the intent-understanding step."""

    intent: CopilotIntent = CopilotIntent.UNKNOWN
    entity_mentions: list[str] = Field(default_factory=list)
    reasoning: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
