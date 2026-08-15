"""Demo connector: a synthetic but realistic enterprise landscape.

Lets the whole platform run locally with no external systems:

    SAP  ->  Databricks  ->  Snowflake  ->  Power BI  ->  KPI

It exercises every capability end to end - technical metadata, SQL-parsed column lineage,
connector-declared lineage, an AI-inferred (unverified) edge, ownership, PII classification
and freshness - so the Copilot has real evidence to reason over.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.connectors.base import (
    ConnectorCapabilities,
    MetadataConnector,
    RawEntity,
    RawLineage,
    RawQualityMetric,
    SqlArtifact,
)
from app.core.constants import (
    EntityType,
    LineageLevel,
    LineageMethod,
    PlatformType,
    QualityDimension,
    QualityStatus,
    RelationshipType,
)
from app.utils.identifiers import build_urn
from app.utils.timestamps import utcnow

SAP = "sap"
DATABRICKS = "databricks"
SNOWFLAKE = "snowflake"
POWERBI = "powerbi"


def _table(
    platform: str,
    qualified_name: str,
    description: str,
    columns: list[dict[str, Any]],
    *,
    entity_type: EntityType = EntityType.TABLE,
    owners: list[tuple[str, str]] | None = None,
    tags: list[str] | None = None,
    row_count: int | None = None,
    properties: dict[str, Any] | None = None,
) -> list[RawEntity]:
    """Build a table (or dataset) plus its columns."""
    entities = [
        RawEntity(
            entity_type=entity_type,
            name=qualified_name.split(".")[-1],
            qualified_name=qualified_name,
            platform=platform,
            description=description,
            owners=owners or [],
            tags=tags or [],
            row_count=row_count,
            properties=properties or {},
        )
    ]
    for index, column in enumerate(columns):
        entities.append(
            RawEntity(
                entity_type=EntityType.COLUMN,
                name=column["name"],
                qualified_name=f"{qualified_name}.{column['name']}",
                platform=platform,
                parent_qualified_name=qualified_name,
                parent_entity_type=entity_type,
                description=column.get("description"),
                data_type=column.get("type", "STRING"),
                ordinal_position=index + 1,
                is_nullable=column.get("nullable", True),
                is_primary_key=column.get("pk", False),
                classifications=column.get("classifications", []),
                business_terms=column.get("terms", []),
            )
        )
    return entities


class DemoConnector(MetadataConnector):
    """Ships the sample SAP -> Databricks -> Snowflake -> Power BI landscape."""

    name = "demo"
    platform = PlatformType.UNKNOWN
    description = "Synthetic enterprise landscape used for local development and demos."
    capabilities = ConnectorCapabilities(
        supports_lineage=True,
        supports_column_lineage=True,
        supports_quality=True,
        supports_incremental=False,
    )
    required_config = ()

    async def test_connection(self) -> tuple[bool, str]:
        return True, "Demo connector is always available."

    # ------------------------------------------------------------------ #
    # Entities
    # ------------------------------------------------------------------ #
    async def extract_entities(self) -> AsyncIterator[RawEntity]:
        for entity in self._entities():
            yield entity

    def _entities(self) -> list[RawEntity]:
        entities: list[RawEntity] = []

        # --- Source systems as containers ------------------------------
        for platform, label, description in (
            (SAP, "SAP ECC", "SAP ERP source system for master and transactional data."),
            (DATABRICKS, "Databricks Lakehouse", "Curation and transformation layer."),
            (SNOWFLAKE, "Snowflake EDW", "Enterprise analytics warehouse."),
            (POWERBI, "Power BI", "Business intelligence and reporting platform."),
        ):
            entities.append(
                RawEntity(
                    entity_type=EntityType.DATA_SOURCE,
                    name=platform,
                    qualified_name=platform,
                    platform=platform,
                    display_name=label,
                    description=description,
                )
            )

        # --- SAP -------------------------------------------------------
        entities += _table(
            SAP,
            "sap.customer",
            "SAP customer master record.",
            [
                {
                    "name": "customer_id",
                    "type": "VARCHAR(18)",
                    "pk": True,
                    "nullable": False,
                    "description": "Unique SAP customer master identifier (KUNNR).",
                    "classifications": ["PII.CustomerIdentifier"],
                    "terms": ["Customer"],
                },
                {
                    "name": "customer_name",
                    "type": "VARCHAR(120)",
                    "description": "Legal customer name.",
                    "classifications": ["PII.Name"],
                },
                {"name": "country", "type": "VARCHAR(3)", "description": "ISO country code."},
                {"name": "created_at", "type": "TIMESTAMP", "description": "Record creation time."},
            ],
            owners=[("Master Data Management", "DATA_OWNER")],
            tags=["source-of-record", "master-data"],
            row_count=1_250_000,
        )
        entities += _table(
            SAP,
            "sap.orders",
            "SAP sales order line items.",
            [
                {"name": "order_id", "type": "VARCHAR(18)", "pk": True, "nullable": False},
                {
                    "name": "customer_id",
                    "type": "VARCHAR(18)",
                    "description": "Customer that placed the order.",
                    "classifications": ["PII.CustomerIdentifier"],
                    "terms": ["Customer"],
                },
                {
                    "name": "amount",
                    "type": "DECIMAL(18,2)",
                    "description": "Net order amount in document currency.",
                    "terms": ["Customer Revenue"],
                },
                {"name": "order_date", "type": "DATE", "description": "Order posting date."},
            ],
            owners=[("Order to Cash", "DATA_OWNER")],
            tags=["source-of-record", "transactional"],
            row_count=48_000_000,
        )

        # --- Databricks -------------------------------------------------
        entities += _table(
            DATABRICKS,
            "databricks.customer_transform",
            "Cleansed and deduplicated customer records produced by the curation notebook.",
            [
                {
                    "name": "customer_id",
                    "type": "STRING",
                    "pk": True,
                    "nullable": False,
                    "description": "Standardised customer identifier.",
                    "classifications": ["PII.CustomerIdentifier"],
                    "terms": ["Customer"],
                },
                {"name": "customer_name", "type": "STRING", "classifications": ["PII.Name"]},
                {"name": "country", "type": "STRING"},
            ],
            owners=[("Data Engineering", "TECHNICAL_OWNER")],
            tags=["curated", "delta"],
            row_count=1_180_000,
            properties={"format": "DELTA", "catalog": "main"},
        )
        entities.append(
            RawEntity(
                entity_type=EntityType.PIPELINE,
                name="customer_etl",
                qualified_name="databricks.customer_etl",
                platform=DATABRICKS,
                description="Nightly job curating SAP customer data into the lakehouse.",
                owners=[("Data Engineering", "TECHNICAL_OWNER")],
                properties={"schedule": "0 2 * * *", "engine": "spark", "last_status": "SUCCESS"},
            )
        )
        entities.append(
            RawEntity(
                entity_type=EntityType.PIPELINE,
                name="sales_load",
                qualified_name="databricks.sales_load",
                platform=DATABRICKS,
                description="Aggregates SAP orders and loads Snowflake sales facts.",
                owners=[("Data Engineering", "TECHNICAL_OWNER")],
                properties={
                    "schedule": "0 3 * * *",
                    "engine": "spark",
                    "last_status": "FAILED",
                    "last_error": "Upstream SAP extract arrived late; job timed out.",
                },
            )
        )

        # --- Snowflake ---------------------------------------------------
        entities += _table(
            SNOWFLAKE,
            "snowflake.customer",
            "Conformed customer dimension in the enterprise warehouse.",
            [
                {
                    "name": "customer_id",
                    "type": "VARCHAR",
                    "pk": True,
                    "nullable": False,
                    "description": "Conformed customer key used across all marts.",
                    "classifications": ["PII.CustomerIdentifier"],
                    "terms": ["Customer"],
                },
                {"name": "customer_name", "type": "VARCHAR", "classifications": ["PII.Name"]},
                {"name": "country", "type": "VARCHAR"},
            ],
            owners=[("Enterprise Analytics", "DATA_OWNER"), ("Jane Okafor", "DATA_STEWARD")],
            tags=["conformed-dimension", "gold"],
            row_count=1_180_000,
        )
        entities += _table(
            SNOWFLAKE,
            "snowflake.sales",
            "Monthly sales fact table aggregated per customer.",
            [
                {"name": "order_month", "type": "DATE", "description": "Month of the order."},
                {
                    "name": "customer_id",
                    "type": "VARCHAR",
                    "description": "Customer key, joins to snowflake.customer.",
                    "classifications": ["PII.CustomerIdentifier"],
                    "terms": ["Customer"],
                },
                {
                    "name": "total_revenue",
                    "type": "DECIMAL(18,2)",
                    "description": "Sum of net order amounts for the month.",
                    "terms": ["Customer Revenue", "Monthly Revenue"],
                },
            ],
            owners=[("Enterprise Analytics", "DATA_OWNER")],
            tags=["fact", "gold", "financial"],
            row_count=14_400_000,
        )

        # --- Power BI -----------------------------------------------------
        entities += _table(
            POWERBI,
            "powerbi.sales_dataset",
            "Power BI semantic model backing executive sales reporting.",
            [
                {
                    "name": "customer_id",
                    "type": "STRING",
                    "classifications": ["PII.CustomerIdentifier"],
                    "terms": ["Customer"],
                },
                {
                    "name": "revenue",
                    "type": "DECIMAL",
                    "description": "Revenue measure surfaced to business users.",
                    "terms": ["Customer Revenue", "Monthly Revenue"],
                },
                {"name": "order_month", "type": "DATE"},
            ],
            entity_type=EntityType.DATASET,
            owners=[("BI Platform", "TECHNICAL_OWNER"), ("Finance Reporting", "BUSINESS_OWNER")],
            tags=["semantic-model", "certified"],
            properties={"refresh_schedule": "0 6 * * *", "workspace": "Finance"},
        )
        entities.append(
            RawEntity(
                entity_type=EntityType.DASHBOARD,
                name="sales_dashboard",
                qualified_name="powerbi.sales_dashboard",
                platform=POWERBI,
                display_name="Executive Sales Dashboard",
                description="Executive view of monthly revenue, customers and growth.",
                owners=[("Finance Reporting", "BUSINESS_OWNER")],
                tags=["executive", "certified"],
                properties={"viewers_30d": 412, "workspace": "Finance"},
            )
        )
        entities.append(
            RawEntity(
                entity_type=EntityType.REPORT,
                name="monthly_revenue_report",
                qualified_name="powerbi.monthly_revenue_report",
                platform=POWERBI,
                display_name="Monthly Revenue Report",
                description="Paginated monthly revenue report distributed to finance leadership.",
                owners=[("Finance Reporting", "BUSINESS_OWNER")],
            )
        )
        entities.append(
            RawEntity(
                entity_type=EntityType.KPI,
                name="monthly_revenue",
                qualified_name="powerbi.kpi.monthly_revenue",
                platform=POWERBI,
                display_name="Monthly Revenue",
                description="Total recognised revenue for a calendar month.",
                owners=[("Finance Reporting", "BUSINESS_OWNER")],
                business_terms=["Monthly Revenue"],
                properties={"unit": "USD", "target": 12_000_000},
            )
        )
        return entities

    # ------------------------------------------------------------------ #
    # SQL - parsed by the lineage service into column-level lineage
    # ------------------------------------------------------------------ #
    async def extract_sql(self) -> AsyncIterator[SqlArtifact]:
        yield SqlArtifact(
            sql=(
                "INSERT INTO snowflake.customer (customer_id, customer_name, country) "
                "SELECT customer_id, customer_name, country "
                "FROM databricks.customer_transform"
            ),
            platform=SNOWFLAKE,
            dialect="snowflake",
            pipeline_urn=build_urn(EntityType.PIPELINE, DATABRICKS, "databricks.customer_etl"),
            source="databricks/customer_etl/load_customer.sql",
        )
        yield SqlArtifact(
            sql=(
                "INSERT INTO snowflake.sales (order_month, customer_id, total_revenue) "
                "SELECT DATE_TRUNC('month', order_date) AS order_month, "
                "customer_id, SUM(amount) AS total_revenue "
                "FROM sap.orders "
                "GROUP BY DATE_TRUNC('month', order_date), customer_id"
            ),
            platform=SNOWFLAKE,
            dialect="snowflake",
            pipeline_urn=build_urn(EntityType.PIPELINE, DATABRICKS, "databricks.sales_load"),
            source="databricks/sales_load/load_sales.sql",
        )
        yield SqlArtifact(
            sql=(
                "CREATE TABLE databricks.customer_transform AS "
                "SELECT customer_id, customer_name, country FROM sap.customer"
            ),
            platform=DATABRICKS,
            dialect="spark",
            pipeline_urn=build_urn(EntityType.PIPELINE, DATABRICKS, "databricks.customer_etl"),
            source="databricks/customer_etl/curate_customer.sql",
        )

    # ------------------------------------------------------------------ #
    # Declared lineage (BI tools rarely expose SQL)
    # ------------------------------------------------------------------ #
    async def extract_lineage(self) -> AsyncIterator[RawLineage]:
        now = utcnow()

        def urn(entity_type: EntityType, platform: str, qualified_name: str) -> str:
            return build_urn(entity_type, platform, qualified_name)

        # Pipelines read from and write to tables.
        for pipeline, reads, writes in (
            ("databricks.customer_etl", "sap.customer", "databricks.customer_transform"),
            ("databricks.sales_load", "sap.orders", "snowflake.sales"),
        ):
            read_platform = SAP
            write_platform = DATABRICKS if writes.startswith(DATABRICKS) else SNOWFLAKE
            yield RawLineage(
                source_urn=urn(EntityType.TABLE, read_platform, reads),
                target_urn=urn(EntityType.PIPELINE, DATABRICKS, pipeline),
                relationship=RelationshipType.READS_FROM,
                level=LineageLevel.TABLE,
                observed_at=now,
                evidence={"source": "databricks job definition"},
            )
            yield RawLineage(
                source_urn=urn(EntityType.PIPELINE, DATABRICKS, pipeline),
                target_urn=urn(EntityType.TABLE, write_platform, writes),
                relationship=RelationshipType.WRITES_TO,
                level=LineageLevel.TABLE,
                observed_at=now,
                evidence={"source": "databricks job definition"},
            )

        # Power BI semantic model consumes Snowflake tables.
        for table in ("snowflake.customer", "snowflake.sales"):
            yield RawLineage(
                source_urn=urn(EntityType.TABLE, SNOWFLAKE, table),
                target_urn=urn(EntityType.DATASET, POWERBI, "powerbi.sales_dataset"),
                relationship=RelationshipType.USES,
                level=LineageLevel.TABLE,
                observed_at=now,
                evidence={"source": "Power BI dataset data source list"},
            )

        # Column-level lineage into the semantic model.
        for source_table, source_column, target_column, transformation in (
            ("snowflake.customer", "customer_id", "customer_id", None),
            ("snowflake.sales", "total_revenue", "revenue", "SUM(total_revenue)"),
            ("snowflake.sales", "order_month", "order_month", None),
        ):
            yield RawLineage(
                source_urn=urn(
                    EntityType.COLUMN, SNOWFLAKE, f"{source_table}.{source_column}"
                ),
                target_urn=urn(
                    EntityType.COLUMN, POWERBI, f"powerbi.sales_dataset.{target_column}"
                ),
                relationship=RelationshipType.DERIVED_FROM,
                level=LineageLevel.COLUMN,
                transformation=transformation,
                observed_at=now,
                evidence={"source": "Power BI model column mapping"},
            )

        # Dataset -> dashboard/report -> KPI.
        yield RawLineage(
            source_urn=urn(EntityType.DATASET, POWERBI, "powerbi.sales_dataset"),
            target_urn=urn(EntityType.DASHBOARD, POWERBI, "powerbi.sales_dashboard"),
            relationship=RelationshipType.USES,
            observed_at=now,
            evidence={"source": "Power BI workspace metadata"},
        )
        yield RawLineage(
            source_urn=urn(EntityType.DATASET, POWERBI, "powerbi.sales_dataset"),
            target_urn=urn(EntityType.REPORT, POWERBI, "powerbi.monthly_revenue_report"),
            relationship=RelationshipType.USES,
            observed_at=now,
            evidence={"source": "Power BI workspace metadata"},
        )
        yield RawLineage(
            source_urn=urn(EntityType.DATASET, POWERBI, "powerbi.sales_dataset"),
            target_urn=urn(EntityType.KPI, POWERBI, "powerbi.kpi.monthly_revenue"),
            relationship=RelationshipType.DEFINED_BY,
            observed_at=now,
            evidence={"source": "KPI definition in the finance metric layer"},
        )
        yield RawLineage(
            source_urn=urn(EntityType.COLUMN, POWERBI, "powerbi.sales_dataset.revenue"),
            target_urn=urn(EntityType.KPI, POWERBI, "powerbi.kpi.monthly_revenue"),
            relationship=RelationshipType.DEFINED_BY,
            level=LineageLevel.COLUMN,
            transformation="SUM(revenue) over calendar month",
            observed_at=now,
            evidence={"source": "KPI definition in the finance metric layer"},
        )

        # An intentionally AI-inferred, unverified edge so the human-validation flow has
        # something to review. It is explicitly marked and carries a low confidence score.
        yield RawLineage(
            source_urn=urn(EntityType.COLUMN, SAP, "sap.customer.country"),
            target_urn=urn(EntityType.COLUMN, POWERBI, "powerbi.sales_dataset.customer_id"),
            relationship=RelationshipType.DERIVED_FROM,
            level=LineageLevel.COLUMN,
            method=LineageMethod.AI_INFERRED,
            confidence=0.42,
            observed_at=now,
            evidence={
                "source": "name-similarity heuristic",
                "note": "Candidate relationship suggested by AI. Requires human verification.",
            },
        )

    # ------------------------------------------------------------------ #
    # Quality and freshness
    # ------------------------------------------------------------------ #
    async def extract_quality(self) -> AsyncIterator[RawQualityMetric]:
        now = utcnow()
        yield RawQualityMetric(
            entity_urn=build_urn(EntityType.TABLE, SNOWFLAKE, "snowflake.sales"),
            dimension=QualityDimension.FRESHNESS,
            metric_name="hours_since_last_load",
            value=31.0,
            unit="hours",
            threshold=24.0,
            status=QualityStatus.FAIL,
            measured_at=now,
            details={
                "expected_interval_hours": 24,
                "reason": "databricks.sales_load failed on its last scheduled run.",
            },
        )
        yield RawQualityMetric(
            entity_urn=build_urn(EntityType.TABLE, SNOWFLAKE, "snowflake.customer"),
            dimension=QualityDimension.FRESHNESS,
            metric_name="hours_since_last_load",
            value=5.0,
            unit="hours",
            threshold=24.0,
            status=QualityStatus.PASS,
            measured_at=now,
            details={"expected_interval_hours": 24},
        )
        yield RawQualityMetric(
            entity_urn=build_urn(EntityType.DATASET, POWERBI, "powerbi.sales_dataset"),
            dimension=QualityDimension.FRESHNESS,
            metric_name="hours_since_last_refresh",
            value=30.0,
            unit="hours",
            threshold=24.0,
            status=QualityStatus.FAIL,
            measured_at=now,
            details={
                "expected_interval_hours": 24,
                "reason": "Scheduled refresh skipped because the upstream fact table was stale.",
            },
        )
        yield RawQualityMetric(
            entity_urn=build_urn(EntityType.TABLE, SAP, "sap.customer"),
            dimension=QualityDimension.COMPLETENESS,
            metric_name="customer_name_null_ratio",
            value=0.004,
            unit="ratio",
            threshold=0.01,
            status=QualityStatus.PASS,
            measured_at=now,
        )
