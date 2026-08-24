"""Copilot agent tests.

Cover the deterministic parts of the pipeline - intent classification, entity-mention
extraction and grounded draft composition. These are what keep answers factual when no model
is available, so they matter more than the phrasing step.

The agent is constructed with a ``None`` session: tool and service constructors only store the
session, and none of the assertions here reach the database.
"""

from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent import MetadataCopilotAgent
from app.agents.prompts.copilot import build_followups, format_evidence
from app.agents.prompts.system import REFUSAL_NO_EVIDENCE
from app.agents.state import AgentState
from app.core.constants import CopilotIntent
from app.schemas.copilot import EvidenceItem, ResolvedEntity
from app.services.metadata.entity_resolution import EntityResolutionService

pytestmark = pytest.mark.unit


@pytest.fixture
def agent() -> MetadataCopilotAgent:
    return MetadataCopilotAgent(cast(AsyncSession, None))


@pytest.fixture
def resolver() -> EntityResolutionService:
    return EntityResolutionService(cast(AsyncSession, None))


class TestIntentClassification:
    @pytest.mark.parametrize(
        ("question", "expected"),
        [
            ("What is customer_id?", CopilotIntent.DEFINITION),
            ("Is customer_id unique?", CopilotIntent.UNIQUENESS),
            ("Where does customer_id come from?", CopilotIntent.UPSTREAM_LINEAGE),
            ("What uses customer_id?", CopilotIntent.DOWNSTREAM_LINEAGE),
            ("What will break if customer_id changes?", CopilotIntent.IMPACT_ANALYSIS),
            ("Which dashboards depend on snowflake.sales?", CopilotIntent.DOWNSTREAM_LINEAGE),
            ("Who owns the sales dataset?", CopilotIntent.OWNERSHIP),
            ("Which datasets contain PII?", CopilotIntent.CLASSIFICATION),
            ("Why is the revenue dashboard stale?", CopilotIntent.QUALITY),
            (
                "What is the business definition of customer revenue?",
                CopilotIntent.GLOSSARY,
            ),
            ("Show me the lineage of the Monthly Revenue KPI.", CopilotIntent.UPSTREAM_LINEAGE),
        ],
    )
    def test_documented_questions_map_to_the_right_intent(
        self, agent: MetadataCopilotAgent, question: str, expected: CopilotIntent
    ) -> None:
        assert agent._rule_based_intent(question) is expected

    def test_unrecognised_question_falls_back_to_discovery(
        self, agent: MetadataCopilotAgent
    ) -> None:
        assert agent._rule_based_intent("zzzz qqqq") is CopilotIntent.DISCOVERY


class TestMentionExtraction:
    def test_asset_names_are_extracted(self, resolver: EntityResolutionService) -> None:
        mentions = resolver.extract_mentions("Where does snowflake.sales.total_revenue come from?")
        assert "snowflake.sales.total_revenue" in mentions

    def test_stopwords_are_ignored(self, resolver: EntityResolutionService) -> None:
        mentions = resolver.extract_mentions("what is the table")
        assert mentions == []

    def test_multi_word_names_are_captured(self, resolver: EntityResolutionService) -> None:
        mentions = resolver.extract_mentions("Show me the monthly revenue KPI")
        assert "monthly revenue" in mentions

    def test_mentions_are_deduplicated(self, resolver: EntityResolutionService) -> None:
        mentions = resolver.extract_mentions("customer_id and customer_id again")
        assert mentions.count("customer_id") == 1


class TestToolPlanning:
    def _state(self, intent: CopilotIntent) -> AgentState:
        state = AgentState(query="test")
        state.intent = intent
        state.resolved_entities = [
            ResolvedEntity.model_validate(
                {
                    "urn": "urn:emc:column:sap:sap.customer.customer_id",
                    "name": "customer_id",
                    "qualified_name": "sap.customer.customer_id",
                    "entity_type": "COLUMN",
                    "platform": "sap",
                    "score": 1.0,
                }
            )
        ]
        return state

    def test_impact_questions_plan_the_impact_tool(self, agent: MetadataCopilotAgent) -> None:
        state = self._state(CopilotIntent.IMPACT_ANALYSIS)
        agent._plan(state)
        assert "impact_analysis" in {step.tool for step in state.plan}

    def test_quality_questions_also_walk_upstream_lineage(
        self, agent: MetadataCopilotAgent
    ) -> None:
        """Staleness is usually caused upstream, so lineage is part of the plan."""
        state = self._state(CopilotIntent.QUALITY)
        agent._plan(state)
        tools = {step.tool for step in state.plan}
        assert {"quality_lookup", "lineage_lookup"} <= tools

    def test_uniqueness_questions_use_the_dedicated_tool(self, agent: MetadataCopilotAgent) -> None:
        state = self._state(CopilotIntent.UNIQUENESS)
        agent._plan(state)
        tools = [step.tool for step in state.plan]
        assert tools[:2] == ["metadata_lookup", "uniqueness_lookup"]

    def test_unresolved_entity_falls_back_to_search(self, agent: MetadataCopilotAgent) -> None:
        state = AgentState(query="something vague")
        agent._plan(state)
        assert [step.tool for step in state.plan] == ["catalog_search"]

    def test_every_planned_tool_exists(self, agent: MetadataCopilotAgent) -> None:
        for intent in CopilotIntent:
            state = self._state(intent)
            agent._plan(state)
            for step in state.plan:
                assert step.tool in agent.tools


class TestDraftComposition:
    def test_draft_without_evidence_refuses(self, agent: MetadataCopilotAgent) -> None:
        state = AgentState(query="What is nonexistent_column?")
        assert agent._compose_draft(state) == REFUSAL_NO_EVIDENCE

    def test_draft_is_built_from_evidence(self, agent: MetadataCopilotAgent) -> None:
        state = AgentState(query="Where does customer_id come from?")
        state.add_evidence(
            [
                EvidenceItem(
                    kind="lineage",
                    title="sap.customer.customer_id -> snowflake.customer.customer_id",
                    detail="Derived via SQL_PARSE with confidence 0.90.",
                    urn="urn:emc:column:snowflake:snowflake.customer.customer_id",
                    source="lineage graph (SQL_PARSE)",
                    confidence=0.9,
                )
            ]
        )
        draft = agent._compose_draft(state)
        assert "Lineage" in draft
        assert "SQL_PARSE" in draft
        assert "Sources:" in draft

    def test_constraint_evidence_is_prioritized_before_lineage(
        self, agent: MetadataCopilotAgent
    ) -> None:
        state = AgentState(query="Is customer_id unique?")
        state.add_evidence(
            [
                EvidenceItem(
                    kind="lineage",
                    title="lineage",
                    detail="Lineage cannot prove uniqueness.",
                    source="lineage graph",
                ),
                EvidenceItem(
                    kind="constraint",
                    title="PRIMARY KEY on sap.customer",
                    detail="customer_id is in the primary key.",
                    source="catalog constraints",
                    constraint_type="PRIMARY KEY",
                    constraint_columns=["customer_id"],
                ),
            ]
        )
        draft = agent._compose_draft(state)
        assert draft.index("Constraints") < draft.index("Lineage")

    def test_inferred_evidence_is_flagged_in_the_draft(self, agent: MetadataCopilotAgent) -> None:
        """An unverified AI guess must never read as an established fact."""
        state = AgentState(query="Where does country come from?")
        state.add_evidence(
            [
                EvidenceItem(
                    kind="lineage",
                    title="sap.customer.country -> powerbi.sales_dataset.customer_id",
                    detail="Suggested by a name-similarity heuristic.",
                    source="lineage graph (AI_INFERRED)",
                    confidence=0.42,
                    inferred=True,
                )
            ]
        )
        assert "AI-inferred, unverified" in agent._compose_draft(state)

    def test_warnings_are_surfaced_as_caveats(self, agent: MetadataCopilotAgent) -> None:
        state = AgentState(query="q")
        state.add_evidence([EvidenceItem(kind="entity", title="t", detail="d", source="catalog")])
        state.add_warnings(["Traversal was truncated at the depth limit."])
        draft = agent._compose_draft(state)
        assert "Caveats" in draft
        assert "truncated" in draft


class TestAgentState:
    def test_evidence_is_deduplicated(self) -> None:
        state = AgentState(query="q")
        item = EvidenceItem(kind="entity", title="t", detail="d", urn="urn:x", source="s")
        state.add_evidence([item, item])
        assert len(state.evidence) == 1

    def test_evidence_budget_is_enforced(self) -> None:
        state = AgentState(query="q", max_evidence=3)
        state.add_evidence(
            [EvidenceItem(kind="entity", title=f"t{i}", detail="d", source="s") for i in range(10)]
        )
        assert len(state.evidence) == 3

    def test_inferred_evidence_is_detected(self) -> None:
        state = AgentState(query="q")
        state.add_evidence(
            [EvidenceItem(kind="lineage", title="t", detail="d", source="s", inferred=True)]
        )
        assert state.has_inferred_evidence is True

    def test_warnings_are_deduplicated(self) -> None:
        state = AgentState(query="q")
        state.add_warnings(["same", "same"])
        assert state.warnings == ["same"]


class TestPromptRendering:
    def test_evidence_is_numbered_for_citation(self) -> None:
        rendered = format_evidence(
            [
                EvidenceItem(kind="entity", title="a", detail="d", source="catalog"),
                EvidenceItem(kind="entity", title="b", detail="d", source="catalog"),
            ]
        )
        assert "[1]" in rendered
        assert "[2]" in rendered

    def test_inferred_evidence_is_labelled_for_the_model(self) -> None:
        rendered = format_evidence(
            [EvidenceItem(kind="lineage", title="a", detail="d", source="s", inferred=True)]
        )
        assert "AI-INFERRED, UNVERIFIED" in rendered

    def test_empty_evidence_is_explicit(self) -> None:
        assert format_evidence([]) == "(no evidence retrieved)"

    def test_followups_reference_the_resolved_asset(self) -> None:
        followups = build_followups(CopilotIntent.DEFINITION.value, "snowflake.sales")
        assert followups
        assert all("snowflake.sales" in question for question in followups)
