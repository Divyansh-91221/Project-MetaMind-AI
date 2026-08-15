"""Enterprise Metadata Copilot agent.

A deterministic, tool-based pipeline::

    User query
      -> intent understanding      (LLM structured output, rule-based fallback)
      -> entity resolution         (catalog search, never model memory)
      -> tool selection            (intent -> explicit tool plan)
      -> retrieval                 (tools call domain services)
      -> evidence construction     (typed, URN-referenced, confidence-tagged)
      -> answer synthesis          (LLM rewrites a grounded draft)

Why not let the model drive? Because lineage and governance answers must be reproducible and
auditable. Tool selection is code, facts come from tools, and the model is confined to
classification and phrasing. The same pipeline maps one-to-one onto LangGraph nodes if a graph
runtime is introduced later.
"""

from __future__ import annotations

import re
import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.prompts.copilot import (
    build_answer_messages,
    build_followups,
    build_intent_messages,
)
from app.agents.prompts.system import REFUSAL_NO_EVIDENCE
from app.agents.state import AgentState, ToolPlanStep
from app.agents.tools import build_toolbox
from app.ai.llm import LLMProvider, get_llm_provider
from app.core.constants import AuditAction, CopilotIntent, Direction, EntityType
from app.core.logging import get_logger
from app.repositories.audit_repository import AuditRepository
from app.schemas.copilot import (
    CopilotChatRequest,
    CopilotChatResponse,
    IntentClassification,
    ResolvedEntity,
)
from app.services.metadata.entity_resolution import EntityResolutionService
from app.utils.identifiers import is_urn

logger = get_logger(__name__)

# Rule-based intent patterns. Ordered: the first match wins, most specific first.
_INTENT_PATTERNS: tuple[tuple[CopilotIntent, re.Pattern[str]], ...] = (
    (
        CopilotIntent.IMPACT_ANALYSIS,
        re.compile(r"\b(break|impact|affected|blast radius|if .*(change|drop|rename|delete))\b"),
    ),
    (
        CopilotIntent.QUALITY,
        re.compile(r"\b(stale|fresh|freshness|out of date|late|quality|failed|failing)\b"),
    ),
    (
        CopilotIntent.CLASSIFICATION,
        re.compile(r"\b(pii|phi|pci|sensitive|sensitivity|classified|classification|gdpr)\b"),
    ),
    (CopilotIntent.OWNERSHIP, re.compile(r"\b(own|owner|owns|steward|accountable|responsible)\b")),
    (
        CopilotIntent.GLOSSARY,
        re.compile(r"\b(business definition|definition of|kpi|metric|means|calculated)\b"),
    ),
    (
        CopilotIntent.DOWNSTREAM_LINEAGE,
        re.compile(r"\b(what uses|who uses|consumes|downstream|depend on this|dashboards? depend)\b"),
    ),
    (
        CopilotIntent.UPSTREAM_LINEAGE,
        re.compile(r"\b(where does .* come from|upstream|source of|sourced|derived from|lineage)\b"),
    ),
    (CopilotIntent.DEFINITION, re.compile(r"\b(what is|what's|describe|explain|tell me about)\b")),
)


class MetadataCopilotAgent:
    """Tool-based agent over the metadata knowledge layer."""

    def __init__(self, session: AsyncSession, llm: LLMProvider | None = None) -> None:
        self.session = session
        self.llm = llm or get_llm_provider()
        self.tools = build_toolbox(session)
        self.resolver = EntityResolutionService(session)
        self.audit_repo = AuditRepository(session)

    # ------------------------------------------------------------------ #
    # Entry point
    # ------------------------------------------------------------------ #
    async def chat(
        self, request: CopilotChatRequest, *, principal: str = "system"
    ) -> CopilotChatResponse:
        started = time.perf_counter()
        state = AgentState(
            query=request.message.strip(),
            conversation_id=request.conversation_id or uuid.uuid4(),
            history=request.history,
            context_urn=request.entity_urn,
            max_evidence=request.max_evidence,
        )

        await self._classify_intent(state)
        await self._resolve_entities(state)
        self._plan(state)
        await self._execute(state)
        await self._synthesize(state)

        response = CopilotChatResponse(
            conversation_id=state.conversation_id,
            answer=state.answer,
            intent=state.intent,
            resolved_entities=state.resolved_entities,
            evidence=state.evidence,
            tool_calls=state.tool_calls,
            suggested_followups=state.followups,
            warnings=state.warnings,
            took_ms=round((time.perf_counter() - started) * 1000, 2),
        )

        await self.audit_repo.record(
            AuditAction.COPILOT_QUERY,
            principal=principal,
            entity_urn=state.primary_urn,
            resource_type="copilot",
            summary=state.query[:500],
            payload={
                "intent": state.intent.value,
                "tools": [trace.tool for trace in state.tool_calls],
                "evidence_count": len(state.evidence),
                "resolved": [entity.urn for entity in state.resolved_entities],
            },
        )
        logger.info(
            "copilot_query_handled",
            extra={
                "intent": state.intent.value,
                "tools": len(state.tool_calls),
                "evidence": len(state.evidence),
                "took_ms": response.took_ms,
            },
        )
        return response

    # ------------------------------------------------------------------ #
    # Stage 1 - intent
    # ------------------------------------------------------------------ #
    async def _classify_intent(self, state: AgentState) -> None:
        classification = await self.llm.structured(
            build_intent_messages(state.query), IntentClassification
        )
        if classification is not None and classification.intent is not CopilotIntent.UNKNOWN:
            state.intent = classification.intent
            state.intent_confidence = classification.confidence
            state.mentions = classification.entity_mentions
            return

        state.intent = self._rule_based_intent(state.query)
        state.intent_confidence = 0.6
        state.mentions = self.resolver.extract_mentions(state.query)

    @staticmethod
    def _rule_based_intent(query: str) -> CopilotIntent:
        """Deterministic fallback so the agent works without any model."""
        lowered = query.lower()
        for intent, pattern in _INTENT_PATTERNS:
            if pattern.search(lowered):
                return intent
        return CopilotIntent.DISCOVERY

    # ------------------------------------------------------------------ #
    # Stage 2 - entity resolution
    # ------------------------------------------------------------------ #
    async def _resolve_entities(self, state: AgentState) -> None:
        resolved: dict[str, ResolvedEntity] = {}

        # Page context (the asset the user is looking at) is the strongest signal.
        if state.context_urn:
            for candidate in await self.resolver.resolve(state.context_urn, limit=1):
                resolved[candidate.urn] = _to_resolved(candidate, score=1.0)

        for mention in state.mentions[:8]:
            if is_urn(mention):
                candidates = await self.resolver.resolve(mention, limit=1)
            else:
                candidates = await self.resolver.resolve(mention, limit=2)
            for candidate in candidates:
                existing = resolved.get(candidate.urn)
                if existing is None or candidate.score > existing.score:
                    resolved[candidate.urn] = _to_resolved(candidate)

        if not resolved:
            for candidate in await self.resolver.resolve_query(state.query, limit=3):
                resolved[candidate.urn] = _to_resolved(candidate)

        state.resolved_entities = sorted(
            resolved.values(), key=lambda entity: entity.score, reverse=True
        )[:5]

        if not state.resolved_entities:
            state.add_warnings(
                ["No catalog asset could be resolved from the question; falling back to search."]
            )

    # ------------------------------------------------------------------ #
    # Stage 3 - tool selection
    # ------------------------------------------------------------------ #
    def _plan(self, state: AgentState) -> None:
        """Map intent (plus resolution outcome) onto an explicit tool plan."""
        urn = state.primary_urn
        if urn is None:
            state.plan = [
                ToolPlanStep(
                    tool="catalog_search",
                    arguments={"query": state.query, "limit": 8},
                    reason="No asset was resolved, so discovery runs first.",
                )
            ]
            return

        plan: list[ToolPlanStep] = []
        intent = state.intent

        if intent is CopilotIntent.DEFINITION:
            plan.append(ToolPlanStep("metadata_lookup", {"urn": urn}, "Explain the asset."))
            plan.append(
                ToolPlanStep("glossary_lookup", {"term": _term_hint(state)}, "Business meaning.")
            )
            plan.append(
                ToolPlanStep(
                    "lineage_lookup",
                    {"urn": urn, "direction": Direction.UPSTREAM.value, "depth": 3},
                    "Origin gives essential context for a definition.",
                )
            )
        elif intent is CopilotIntent.UPSTREAM_LINEAGE:
            plan.append(ToolPlanStep("metadata_lookup", {"urn": urn}, "Identify the asset."))
            plan.append(
                ToolPlanStep(
                    "lineage_lookup",
                    {"urn": urn, "direction": Direction.UPSTREAM.value, "depth": 6},
                    "Trace the sources.",
                )
            )
        elif intent is CopilotIntent.DOWNSTREAM_LINEAGE:
            plan.append(ToolPlanStep("metadata_lookup", {"urn": urn}, "Identify the asset."))
            plan.append(
                ToolPlanStep(
                    "lineage_lookup",
                    {"urn": urn, "direction": Direction.DOWNSTREAM.value, "depth": 6},
                    "Trace the consumers.",
                )
            )
        elif intent is CopilotIntent.IMPACT_ANALYSIS:
            plan.append(ToolPlanStep("metadata_lookup", {"urn": urn}, "Identify the asset."))
            plan.append(
                ToolPlanStep("impact_analysis", {"urn": urn, "depth": 8}, "Compute blast radius.")
            )
        elif intent is CopilotIntent.OWNERSHIP:
            plan.append(ToolPlanStep("governance_lookup", {"urn": urn}, "Ownership and stewardship."))
            plan.append(ToolPlanStep("metadata_lookup", {"urn": urn}, "Asset context."))
        elif intent is CopilotIntent.CLASSIFICATION:
            if _asks_for_sensitive_inventory(state.query):
                plan.append(
                    ToolPlanStep(
                        "governance_lookup",
                        {"sensitivity": _sensitivity_hint(state.query), "limit": 25},
                        "Inventory of sensitive assets.",
                    )
                )
            plan.append(ToolPlanStep("governance_lookup", {"urn": urn}, "Classification profile."))
        elif intent is CopilotIntent.QUALITY:
            plan.append(
                ToolPlanStep("quality_lookup", {"urn": urn, "explain": True}, "Freshness and cause.")
            )
            plan.append(
                ToolPlanStep(
                    "lineage_lookup",
                    {"urn": urn, "direction": Direction.UPSTREAM.value, "depth": 5},
                    "Root cause is usually upstream.",
                )
            )
        elif intent is CopilotIntent.GLOSSARY:
            plan.append(
                ToolPlanStep("glossary_lookup", {"term": _term_hint(state)}, "Business definition.")
            )
            plan.append(
                ToolPlanStep(
                    "lineage_lookup",
                    {"urn": urn, "direction": Direction.UPSTREAM.value, "depth": 5},
                    "How the metric is produced.",
                )
            )
        else:
            plan.append(
                ToolPlanStep("catalog_search", {"query": state.query, "limit": 8}, "Discovery.")
            )
            plan.append(ToolPlanStep("metadata_lookup", {"urn": urn}, "Best-matching asset."))

        state.plan = plan

    # ------------------------------------------------------------------ #
    # Stage 4 - execution
    # ------------------------------------------------------------------ #
    async def _execute(self, state: AgentState) -> None:
        for step in state.plan:
            tool = self.tools.get(step.tool)
            if tool is None:
                state.add_warnings([f"Unknown tool '{step.tool}' in plan."])
                continue
            result, trace = await tool.invoke(**step.arguments)
            state.tool_calls.append(trace)
            state.add_evidence(result.evidence)
            state.add_warnings(result.warnings)

        # If the plan produced nothing usable, fall back to discovery once.
        if not state.evidence and "catalog_search" not in {t.tool for t in state.tool_calls}:
            result, trace = await self.tools["catalog_search"].invoke(query=state.query, limit=8)
            state.tool_calls.append(trace)
            state.add_evidence(result.evidence)
            state.add_warnings(result.warnings)

    # ------------------------------------------------------------------ #
    # Stage 5 - synthesis
    # ------------------------------------------------------------------ #
    async def _synthesize(self, state: AgentState) -> None:
        draft = self._compose_draft(state)
        state.followups = build_followups(
            state.intent.value,
            state.primary_entity.qualified_name if state.primary_entity else None,
        )

        if not state.evidence:
            state.answer = REFUSAL_NO_EVIDENCE
            return

        response = await self.llm.complete(build_answer_messages(state, draft))
        state.answer = response.content.strip() or draft

    def _compose_draft(self, state: AgentState) -> str:
        """Build a factual answer directly from evidence.

        This is the safety net: it guarantees a grounded answer even when no model is
        available, and it gives the model a factual skeleton it cannot drift from.
        """
        if not state.evidence:
            return REFUSAL_NO_EVIDENCE

        lines: list[str] = []
        entity = state.primary_entity
        if entity is not None:
            lines.append(
                f"**{entity.qualified_name}** ({entity.entity_type.lower()} on {entity.platform})"
            )

        grouped: dict[str, list[str]] = {}
        for index, item in enumerate(state.evidence, start=1):
            flag = " _(AI-inferred, unverified)_" if item.inferred else ""
            grouped.setdefault(item.kind, []).append(f"- {item.detail}{flag} [{index}]")

        headings = {
            "entity": "Definition",
            "glossary": "Business meaning",
            "lineage": "Lineage",
            "impact": "Impact",
            "governance": "Governance",
            "quality": "Data quality",
            "document": "Documentation",
        }
        for kind, heading in headings.items():
            if kind in grouped:
                lines.append(f"\n**{heading}**")
                lines.extend(grouped[kind][:12])

        if state.warnings:
            lines.append("\n**Caveats**")
            lines.extend(f"- {warning}" for warning in state.warnings)

        lines.append(
            "\n_Sources: "
            + ", ".join(
                sorted({item.source for item in state.evidence if item.source})
            )
            + "._"
        )
        return "\n".join(lines)


# --------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------- #
def _to_resolved(candidate: object, *, score: float | None = None) -> ResolvedEntity:
    entity = candidate.entity  # type: ignore[attr-defined]
    return ResolvedEntity(
        urn=entity.urn,
        name=entity.name,
        qualified_name=entity.qualified_name,
        entity_type=entity.entity_type.value,
        platform=entity.platform,
        score=score if score is not None else candidate.score,  # type: ignore[attr-defined]
    )


def _term_hint(state: AgentState) -> str:
    """Best guess at the business term the user means.

    Prefers a resolved KPI, then the raw mention text, then the whole question.
    """
    for entity in state.resolved_entities:
        if entity.entity_type == EntityType.KPI.value:
            return entity.name.replace("_", " ")
    if state.mentions:
        return state.mentions[0].replace("_", " ")
    return state.query


def _asks_for_sensitive_inventory(query: str) -> bool:
    lowered = query.lower()
    return any(word in lowered for word in ("which", "list", "what datasets", "what tables"))


def _sensitivity_hint(query: str) -> str:
    lowered = query.lower()
    for tag in ("pii", "phi", "pci", "financial"):
        if tag in lowered:
            return tag.upper()
    return "PII"
