"""End-to-end smoke suite (Phase 12).

Exercises every capability the product claims to have, against a real PostgreSQL schema:
metadata, search, lineage, impact, governance, glossary, quality, Copilot and uniqueness.
Skips (rather than fails) when PostgreSQL is unreachable, matching the rest of the
integration suite - `docker compose up -d postgres` then `pytest -m integration`.

This file intentionally stays independent from ``test_ingestion_flow.py`` so it reads as a
single checklist a reviewer can run end to end.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent import MetadataCopilotAgent
from app.core.constants import CopilotIntent, QualityDimension, QualityStatus
from app.schemas.copilot import CopilotChatRequest
from app.schemas.glossary import BusinessTermCreate
from app.schemas.governance import ClassificationReviewRequest, SensitiveAssetsQuery
from app.schemas.metadata import HealthScoreBreakdown
from app.schemas.quality import QualityMetricCreate
from app.services.glossary.glossary_service import GlossaryService
from app.services.governance.governance_service import GovernanceService
from app.services.impact.impact_service import ImpactService
from app.services.metadata.metadata_service import MetadataService
from app.services.quality.quality_service import QualityService
from app.services.search.hybrid_search import SearchService

pytestmark = pytest.mark.integration

CUSTOMER_ID = "urn:emc:column:sap:sap.customer.customer_id"
CUSTOMER_TABLE = "urn:emc:table:sap:sap.customer"
SNOWFLAKE_SALES = "urn:emc:table:snowflake:snowflake.sales"


class TestSmokeSuite:
    """One test method per checklist item in the Phase 12 smoke plan."""

    async def test_01_metadata_api_works(self, ingested: AsyncSession) -> None:
        summary = await MetadataService(ingested).catalog_summary()
        assert summary["entities_by_type"]

        detail = await MetadataService(ingested).get_entity_detail(CUSTOMER_ID)
        assert detail.is_primary_key is True

    async def test_02_search_works(self, ingested: AsyncSession) -> None:
        from app.schemas.search import SearchRequest

        response = await SearchService(ingested).search(SearchRequest(q="customer", limit=10))
        assert response.hits

    async def test_03_lineage_works(self, ingested: AsyncSession) -> None:
        from app.core.constants import Direction
        from app.schemas.lineage import LineageQuery
        from app.services.lineage.lineage_service import LineageService

        graph = await LineageService(ingested).get_lineage(
            CUSTOMER_ID, direction=Direction.DOWNSTREAM, query=LineageQuery(depth=6)
        )
        assert graph.nodes

    async def test_04_impact_analysis_works(self, ingested: AsyncSession) -> None:
        result = await ImpactService(ingested).analyze(SNOWFLAKE_SALES, depth=8)
        assert result.summary.total_impacted >= 0

    async def test_05_governance_works(self, ingested: AsyncSession) -> None:
        service = GovernanceService(ingested)
        profile = await service.get_profile(CUSTOMER_ID)
        assert profile.entity_urn == CUSTOMER_ID

        sensitive = await service.sensitive_assets(SensitiveAssetsQuery(limit=10))
        assert sensitive

        row = sensitive[0]
        reviewed = await service.review_classification(
            row.assignment_id,
            ClassificationReviewRequest(status="CONFIRMED"),
            principal="smoke-test",
        )
        assert reviewed.confirmed is True

        # Confirming a classification must leave an audit trail behind.
        from app.core.constants import AuditAction
        from app.repositories.audit_repository import AuditRepository

        events = await AuditRepository(ingested).list_events(
            action=AuditAction.CLASSIFICATION_CONFIRMED, limit=5
        )
        assert events

    async def test_06_glossary_works(self, ingested: AsyncSession) -> None:
        service = GlossaryService(ingested)
        await service.create_term(
            BusinessTermCreate(
                name="Smoke Test Term",
                domain="smoke",
                definition="A term created purely to prove the glossary API works end to end.",
            )
        )
        hits = await service.search("Smoke Test", limit=5)
        assert any(term.name == "Smoke Test Term" for term in hits)

    async def test_07_quality_works(self, ingested: AsyncSession) -> None:
        service = QualityService(ingested)
        await service.record_metric(
            QualityMetricCreate(
                entity_urn=SNOWFLAKE_SALES,
                dimension=QualityDimension.COMPLETENESS,
                metric_name="null_rate",
                value=0.01,
                status=QualityStatus.PASS,
            )
        )
        profile = await service.get_profile(SNOWFLAKE_SALES)
        assert profile.metrics

        stale = await service.stale_assets(limit=10)
        assert isinstance(stale, list)

    async def test_08_copilot_works(self, ingested: AsyncSession) -> None:
        response = await MetadataCopilotAgent(ingested).chat(
            CopilotChatRequest(message="What is customer_id?"),
            principal="smoke-test",
        )
        assert response.answer
        assert response.evidence

    async def test_09_uniqueness_works(self, ingested: AsyncSession) -> None:
        response = await MetadataCopilotAgent(ingested).chat(
            CopilotChatRequest(
                message="Is customer_id unique?",
                entity_urn=CUSTOMER_ID,
            ),
            principal="smoke-test",
        )
        assert response.intent is CopilotIntent.UNIQUENESS
        assert any(item.kind == "constraint" for item in response.evidence)

    async def test_10_health_score_works(self, ingested: AsyncSession) -> None:
        breakdown = await MetadataService(ingested).get_health_score(CUSTOMER_TABLE)
        assert isinstance(breakdown, HealthScoreBreakdown)
        assert 0 <= breakdown.total <= 100

    async def test_11_ingestion_run_history_works(self, ingested: AsyncSession) -> None:
        from app.core.constants import AuditAction
        from app.ingestion.run_history import group_ingestion_events
        from app.repositories.audit_repository import AuditRepository

        events = await AuditRepository(ingested).list_events(
            actions=[AuditAction.INGESTION_STARTED, AuditAction.INGESTION_COMPLETED],
            limit=50,
        )
        runs = group_ingestion_events(events)
        assert runs
        assert runs[0]["connector"] == "demo"

    async def test_12_demo_reset_job_reingests_cleanly(self, ingested: AsyncSession) -> None:
        """Standing in for "backend starts / migration succeeds / demo data seeds": re-running
        the same ingestion job that powers the reset button must stay idempotent."""
        from app.ingestion.pipeline import IngestionPipeline
        from app.schemas.metadata import IngestionRequest

        result = await IngestionPipeline(ingested).run(
            IngestionRequest(connector="demo", data_source_name="demo-test", full_refresh=True),
            principal="smoke-test",
        )
        assert result.entities_created == 0  # idempotent: nothing new to create
        assert not result.errors
