"""Prompt construction for the Copilot.

The synthesis prompt carries three things: the question, the retrieved evidence, and a
deterministic draft answer built from that evidence. The model's job is to make the draft
read well - not to add facts. With the offline ``mock`` provider the draft is returned
unchanged, which keeps the system useful and grounded without any model access.
"""

from __future__ import annotations

from app.agents.state import AgentState
from app.ai.llm import LLMMessage
from app.agents.prompts.system import INTENT_SYSTEM_PROMPT, SYSTEM_PROMPT
from app.schemas.copilot import EvidenceItem

MAX_EVIDENCE_CHARS = 8000


def build_intent_messages(query: str) -> list[LLMMessage]:
    return [
        LLMMessage(role="system", content=INTENT_SYSTEM_PROMPT),
        LLMMessage(role="user", content=query),
    ]


def format_evidence(evidence: list[EvidenceItem]) -> str:
    """Render evidence as a numbered, citable list."""
    lines: list[str] = []
    budget = MAX_EVIDENCE_CHARS
    for index, item in enumerate(evidence, start=1):
        flags: list[str] = []
        if item.inferred:
            flags.append("AI-INFERRED, UNVERIFIED")
        if item.confidence < 1.0:
            flags.append(f"confidence {item.confidence:.2f}")
        suffix = f" [{'; '.join(flags)}]" if flags else ""
        line = (
            f"[{index}] ({item.kind}) {item.title}{suffix}\n"
            f"    {item.detail}\n"
            f"    source: {item.source}"
            + (f" | urn: {item.urn}" if item.urn else "")
        )
        budget -= len(line)
        if budget <= 0:
            lines.append("[...] evidence truncated to fit the context window.")
            break
        lines.append(line)
    return "\n".join(lines) if lines else "(no evidence retrieved)"


def build_answer_messages(state: AgentState, draft: str) -> list[LLMMessage]:
    """Assemble the grounded synthesis request."""
    history = "\n".join(
        f"{message.role}: {message.content}" for message in state.history[-6:]
    )
    warnings = "\n".join(f"- {warning}" for warning in state.warnings)

    user_content = f"""\
QUESTION
{state.query}

RESOLVED ASSETS
{_format_entities(state)}

EVIDENCE
{format_evidence(state.evidence)}

CAVEATS
{warnings or "(none)"}

CONVERSATION SO FAR
{history or "(new conversation)"}

A grounded draft answer has already been assembled from the evidence above. Rewrite it so it \
reads clearly and directly. Do not add any fact that is not in the evidence. Preserve every \
caveat about inferred or unverified lineage.

<draft>
{draft}
</draft>
"""
    return [
        LLMMessage(role="system", content=SYSTEM_PROMPT),
        LLMMessage(role="user", content=user_content),
    ]


def _format_entities(state: AgentState) -> str:
    if not state.resolved_entities:
        return "(none resolved)"
    return "\n".join(
        f"- {entity.qualified_name} ({entity.entity_type}, {entity.platform}) urn={entity.urn}"
        for entity in state.resolved_entities
    )


FOLLOWUP_TEMPLATES: dict[str, list[str]] = {
    "DEFINITION": [
        "Where does {name} come from?",
        "What uses {name}?",
        "Who owns {name}?",
    ],
    "UPSTREAM_LINEAGE": [
        "What will break if {name} changes?",
        "Is {name} fresh?",
        "Show the business definition behind {name}.",
    ],
    "DOWNSTREAM_LINEAGE": [
        "What will break if {name} changes?",
        "Who owns the downstream dashboards of {name}?",
    ],
    "IMPACT_ANALYSIS": [
        "Who should I notify about a change to {name}?",
        "Which of those paths are AI-inferred?",
    ],
    "OWNERSHIP": [
        "What does {name} contain?",
        "Is {name} classified as sensitive?",
    ],
    "CLASSIFICATION": [
        "Which dashboards expose {name}?",
        "Which policies apply to {name}?",
    ],
    "QUALITY": [
        "What is upstream of {name}?",
        "Which dashboards are affected while {name} is stale?",
    ],
    "GLOSSARY": [
        "Which assets implement {name}?",
        "Show me the lineage of {name}.",
    ],
    "DISCOVERY": [
        "What is {name}?",
        "Who owns {name}?",
    ],
}


def build_followups(intent: str, name: str | None) -> list[str]:
    """Suggest next questions, grounded in the asset that was actually resolved."""
    if not name:
        return [
            "Which datasets contain PII?",
            "Show me the lineage of the Monthly Revenue KPI.",
            "Which dashboards depend on snowflake.sales?",
        ]
    return [template.format(name=name) for template in FOLLOWUP_TEMPLATES.get(intent, [])][:3]
