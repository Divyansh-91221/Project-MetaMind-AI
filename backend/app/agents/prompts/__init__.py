"""Prompt templates. Behaviour lives here; business rules live in code."""

from app.agents.prompts.copilot import (
    build_answer_messages,
    build_followups,
    build_intent_messages,
    format_evidence,
)
from app.agents.prompts.system import (
    INTENT_SYSTEM_PROMPT,
    REFUSAL_NO_EVIDENCE,
    SYSTEM_PROMPT,
)

__all__ = [
    "INTENT_SYSTEM_PROMPT",
    "REFUSAL_NO_EVIDENCE",
    "SYSTEM_PROMPT",
    "build_answer_messages",
    "build_followups",
    "build_intent_messages",
    "format_evidence",
]
