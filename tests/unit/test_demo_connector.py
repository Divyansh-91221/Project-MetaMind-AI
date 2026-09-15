"""Demo connector tests.

The demo landscape is what every local run, screenshot and Copilot answer depends on, so its
shape is treated as a contract: the SAP -> Databricks -> Snowflake -> Power BI chain must stay
intact, and the deliberately AI-inferred edge must stay low-confidence and unverified.
"""

from __future__ import annotations

import pytest

from app.connectors.base import RawEntity, RawLineage, RawQualityMetric, SqlArtifact
from app.connectors.demo import DemoConnector
from app.connectors.registry import create_connector, list_connectors
from app.core.constants import (
    EntityType,
    LineageMethod,
    QualityDimension,
    QualityStatus,
    RelationshipType,
)

pytestmark = pytest.mark.unit


@pytest.fixture
async def entities(demo_connector: DemoConnector) -> list[RawEntity]:
    return [entity async for entity in demo_connector.extract_entities()]


@pytest.fixture
async def lineage(demo_connector: DemoConnector) -> list[RawLineage]:
    return [edge async for edge in demo_connector.extract_lineage()]


class TestEntities:
    async def test_every_documented_asset_is_present(self, entities: list[RawEntity]) -> None:
        qualified_names = {entity.qualified_name for entity in entities}
        assert {
            "sap.customer",
            "sap.orders",
            "databricks.customer_transform",
            "databricks.payments_transform",
            "snowflake.customer",
            "snowflake.sales",
            "powerbi.sales_dataset",
            "powerbi.sales_dashboard",
            "powerbi.kpi.monthly_revenue",
        } <= qualified_names

    async def test_urns_are_unique(self, entities: list[RawEntity]) -> None:
        urns = [entity.urn for entity in entities]
        assert len(urns) == len(set(urns))

    async def test_columns_declare_their_parent_table(self, entities: list[RawEntity]) -> None:
        columns = [e for e in entities if e.entity_type is EntityType.COLUMN]
        assert columns
        assert all(column.parent_urn is not None for column in columns)

    async def test_column_parents_exist_in_the_same_extraction(
        self, entities: list[RawEntity]
    ) -> None:
        """A dangling parent reference would break the catalog hierarchy on ingestion."""
        urns = {entity.urn for entity in entities}
        for column in (e for e in entities if e.entity_type is EntityType.COLUMN):
            assert column.parent_urn in urns

    async def test_pipelines_are_catalogued(self, entities: list[RawEntity]) -> None:
        pipelines = {e.qualified_name for e in entities if e.entity_type is EntityType.PIPELINE}
        assert pipelines == {
            "databricks.customer_etl",
            "databricks.sales_load",
            "databricks.payments_etl",
        }

    async def test_sensitive_columns_carry_classifications(self, entities: list[RawEntity]) -> None:
        customer_id = next(e for e in entities if e.qualified_name == "sap.customer.customer_id")
        assert "PII.CustomerIdentifier" in customer_id.classifications

    async def test_assets_declare_owners(self, entities: list[RawEntity]) -> None:
        sales = next(e for e in entities if e.qualified_name == "snowflake.sales")
        assert sales.owners


class TestSqlArtifacts:
    async def test_sql_is_exposed_for_the_lineage_parser(
        self, demo_connector: DemoConnector
    ) -> None:
        artifacts = [artifact async for artifact in demo_connector.extract_sql()]
        assert len(artifacts) == 4
        assert all(isinstance(artifact, SqlArtifact) for artifact in artifacts)
        assert all(artifact.pipeline_urn for artifact in artifacts)

    async def test_sql_parses_into_column_lineage(self, demo_connector: DemoConnector) -> None:
        from app.services.lineage.sql_lineage_parser import SqlLineageParser

        parser = SqlLineageParser()
        column_edges = [
            edge
            async for artifact in demo_connector.extract_sql()
            for edge in parser.parse(artifact).column_edges
        ]
        targets = {edge.target_urn for edge in column_edges}
        assert "urn:emc:column:snowflake:snowflake.sales.total_revenue" in targets


class TestLineage:
    async def test_customer_id_chain_is_connected(self, lineage: list[RawLineage]) -> None:
        edges = {(edge.source_urn, edge.target_urn) for edge in lineage}
        assert (
            "urn:emc:column:snowflake:snowflake.customer.customer_id",
            "urn:emc:column:powerbi:powerbi.sales_dataset.customer_id",
        ) in edges

    async def test_revenue_chain_reaches_the_kpi(self, lineage: list[RawLineage]) -> None:
        edges = {(edge.source_urn, edge.target_urn) for edge in lineage}
        assert (
            "urn:emc:column:powerbi:powerbi.sales_dataset.revenue",
            "urn:emc:kpi:powerbi:powerbi.kpi.monthly_revenue",
        ) in edges

    async def test_pipelines_read_and_write(self, lineage: list[RawLineage]) -> None:
        relationships = {edge.relationship for edge in lineage}
        assert RelationshipType.READS_FROM in relationships
        assert RelationshipType.WRITES_TO in relationships

    async def test_no_self_referencing_edges(self, lineage: list[RawLineage]) -> None:
        assert all(edge.source_urn != edge.target_urn for edge in lineage)

    async def test_the_inferred_edge_is_marked_and_low_confidence(
        self, lineage: list[RawLineage]
    ) -> None:
        inferred = [e for e in lineage if e.method is LineageMethod.AI_INFERRED]
        assert len(inferred) == 1
        assert inferred[0].confidence is not None
        assert inferred[0].confidence < 0.5
        assert "verification" in str(inferred[0].evidence).lower()

    async def test_declared_edges_carry_evidence(self, lineage: list[RawLineage]) -> None:
        assert all(edge.evidence.get("source") for edge in lineage)


class TestQuality:
    @pytest.fixture
    async def metrics(self, demo_connector: DemoConnector) -> list[RawQualityMetric]:
        return [metric async for metric in demo_connector.extract_quality()]

    async def test_a_stale_asset_is_reported(self, metrics: list[RawQualityMetric]) -> None:
        """The demo must reproduce the "why is the dashboard stale?" scenario."""
        failing = [m for m in metrics if m.status is QualityStatus.FAIL]
        assert any("snowflake.sales" in m.entity_urn for m in failing)

    async def test_freshness_metrics_declare_a_threshold(
        self, metrics: list[RawQualityMetric]
    ) -> None:
        freshness = [m for m in metrics if m.dimension is QualityDimension.FRESHNESS]
        assert freshness
        assert all(metric.threshold for metric in freshness)


class TestRegistry:
    async def test_demo_connector_is_registered(self) -> None:
        assert isinstance(create_connector("demo"), DemoConnector)

    async def test_connector_names_are_unique(self) -> None:
        names = [connector.name for connector in list_connectors()]
        assert len(names) == len(set(names))

    async def test_unknown_connector_raises_not_found(self) -> None:
        from app.core.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            create_connector("does-not-exist")

    async def test_connection_test_succeeds_offline(self, demo_connector: DemoConnector) -> None:
        success, _ = await demo_connector.test_connection()
        assert success is True
