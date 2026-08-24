"""End-to-end ingestion integration test.

Exercises the real path: demo connector -> normalisation -> PostgreSQL -> lineage graph ->
traversal -> impact analysis -> Copilot answer. This is the test that proves the layers
actually fit together.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import Direction, EntityType, LineageMethod
from app.graph.base import InMemoryGraphStore
from app.ingestion.pipeline import IngestionPipeline
from app.schemas.copilot import CopilotChatRequest
from app.schemas.lineage import LineageQuery
from app.schemas.metadata import IngestionRequest
from app.schemas.search import SearchRequest
from app.services.impact.impact_service import ImpactService
from app.services.lineage.lineage_service import LineageService
from app.services.metadata.metadata_service import MetadataService
from app.services.search.hybrid_search import SearchService

pytestmark = pytest.mark.integration

CUSTOMER_ID = "urn:emc:column:sap:sap.customer.customer_id"
SNOWFLAKE_SALES = "urn:emc:table:snowflake:snowflake.sales"
DATASET_REVENUE = "urn:emc:column:powerbi:powerbi.sales_dataset.revenue"


class TestIngestion:
    async def test_catalog_is_populated(self, ingested: AsyncSession) -> None:
        summary = await MetadataService(ingested).catalog_summary()
        assert summary["entities_by_type"][EntityType.TABLE.value] > 0
        assert summary["entities_by_type"][EntityType.COLUMN.value] > 0

    async def test_ingestion_is_idempotent(self, ingested: AsyncSession) -> None:
        """Re-running must update rather than duplicate, thanks to URN-derived keys."""
        before = await MetadataService(ingested).catalog_summary()
        result = await IngestionPipeline(ingested).run(
            IngestionRequest(connector="demo", data_source_name="demo-test"),
            principal="integration-test",
        )
        after = await MetadataService(ingested).catalog_summary()
        assert result.entities_created == 0
        assert after["entities_by_type"] == before["entities_by_type"]

    async def test_asset_detail_includes_columns_and_governance(
        self, ingested: AsyncSession
    ) -> None:
        detail = await MetadataService(ingested).get_entity_detail(SNOWFLAKE_SALES)
        assert {column.name for column in detail.columns} >= {"customer_id", "total_revenue"}
        assert detail.owners


class TestLineage:
    async def test_sql_parsed_column_lineage_is_persisted(self, ingested: AsyncSession) -> None:
        edges = await LineageService(ingested).get_direct_edges(
            "urn:emc:column:snowflake:snowflake.sales.total_revenue"
        )
        methods = {edge.method for edge in edges}
        assert LineageMethod.SQL_PARSE in methods
        assert any(edge.transformation == "SUM(amount)" for edge in edges)

    async def test_upstream_traversal_reaches_the_source_system(
        self, ingested: AsyncSession
    ) -> None:
        graph = await LineageService(ingested).get_lineage(
            DATASET_REVENUE, direction=Direction.UPSTREAM, query=LineageQuery(depth=8)
        )
        platforms = {node.platform for node in graph.nodes}
        assert "sap" in platforms

    async def test_downstream_traversal_reaches_the_kpi(self, ingested: AsyncSession) -> None:
        graph = await LineageService(ingested).get_lineage(
            CUSTOMER_ID, direction=Direction.DOWNSTREAM, query=LineageQuery(depth=8)
        )
        assert any(node.entity_type is EntityType.DATASET for node in graph.nodes)

    async def test_inferred_edges_land_in_the_review_queue(self, ingested: AsyncSession) -> None:
        queue = await LineageService(ingested).review_queue(limit=50)
        assert any(edge.method is LineageMethod.AI_INFERRED for edge in queue)


class TestImpactAndSearch:
    async def test_impact_identifies_downstream_bi_assets(self, ingested: AsyncSession) -> None:
        result = await ImpactService(ingested).analyze(SNOWFLAKE_SALES, depth=8)
        assert result.summary.total_impacted > 0
        assert result.impacted_assets

    async def test_search_finds_assets_by_keyword(self, ingested: AsyncSession) -> None:
        response = await SearchService(ingested).search(SearchRequest(q="total_revenue", limit=10))
        assert any("snowflake.sales" in hit.qualified_name for hit in response.hits)


class TestCopilot:
    async def test_answers_are_grounded_in_evidence(self, ingested: AsyncSession) -> None:
        from app.agents.agent import MetadataCopilotAgent

        response = await MetadataCopilotAgent(ingested).chat(
            CopilotChatRequest(message="Where does total_revenue come from?"),
            principal="integration-test",
        )
        assert response.evidence
        assert response.answer
        assert response.tool_calls

    async def test_impact_question_reports_affected_assets(self, ingested: AsyncSession) -> None:
        from app.agents.agent import MetadataCopilotAgent

        response = await MetadataCopilotAgent(ingested).chat(
            CopilotChatRequest(message="What will break if snowflake.sales changes?"),
            principal="integration-test",
        )
        assert any(item.kind == "impact" for item in response.evidence)


class TestGraphRebuild:
    async def test_graph_can_be_rebuilt_from_postgres(self, ingested: AsyncSession) -> None:
        """PostgreSQL is the source of truth: the projection must be reproducible."""
        service = LineageService(ingested, graph=InMemoryGraphStore())
        stats = await service.rebuild_graph(principal="integration-test")
        assert stats["nodes"] > 0
        assert stats["edges"] > 0
