"""SQL lineage extraction tests.

These lock in the behaviour that makes lineage trustworthy: real column-level resolution,
captured transformations, and *refusal* to guess when the SQL is ambiguous.
"""

from __future__ import annotations

import pytest

from app.connectors.base import SqlArtifact
from app.core.constants import LineageLevel, LineageMethod
from app.services.lineage.sql_lineage_parser import SqlLineageParser

pytestmark = pytest.mark.unit


@pytest.fixture
def parser() -> SqlLineageParser:
    return SqlLineageParser()


def _artifact(sql: str, **kwargs: object) -> SqlArtifact:
    defaults: dict[str, object] = {"platform": "generic_sql", "source": "test"}
    defaults.update(kwargs)
    return SqlArtifact(sql=sql, **defaults)  # type: ignore[arg-type]


class TestInsertSelect:
    def test_resolves_table_and_column_lineage(self, parser: SqlLineageParser) -> None:
        out = parser.parse(
            _artifact(
                "INSERT INTO snowflake.customer (customer_id, customer_name, country) "
                "SELECT customer_id, customer_name, country "
                "FROM databricks.customer_transform",
                platform="snowflake",
                dialect="snowflake",
            )
        )

        assert out.statements_parsed == 1
        assert out.warnings == []

        assert [(e.source_urn, e.target_urn) for e in out.table_edges] == [
            (
                "urn:emc:table:databricks:databricks.customer_transform",
                "urn:emc:table:snowflake:snowflake.customer",
            )
        ]
        assert len(out.column_edges) == 3
        assert all(edge.level is LineageLevel.COLUMN for edge in out.column_edges)
        assert all(edge.method is LineageMethod.SQL_PARSE for edge in out.column_edges)

    def test_emits_one_table_edge_per_distinct_source(self, parser: SqlLineageParser) -> None:
        """The alias map holds several keys per table; edges must not be duplicated."""
        out = parser.parse(
            _artifact(
                "INSERT INTO mart.x (a) SELECT c.customer_id FROM sap.customer c "
                "JOIN sap.orders o ON o.customer_id = c.customer_id"
            )
        )
        sources = [edge.source_urn for edge in out.table_edges]
        assert sorted(sources) == [
            "urn:emc:table:sap:sap.customer",
            "urn:emc:table:sap:sap.orders",
        ]

    def test_captures_aggregate_transformation(self, parser: SqlLineageParser) -> None:
        out = parser.parse(
            _artifact(
                "INSERT INTO snowflake.sales (order_month, customer_id, total_revenue) "
                "SELECT DATE_TRUNC('month', order_date) AS order_month, "
                "customer_id, SUM(amount) AS total_revenue "
                "FROM sap.orders GROUP BY DATE_TRUNC('month', order_date), customer_id",
                platform="snowflake",
                dialect="snowflake",
            )
        )

        by_target = {edge.target_urn: edge for edge in out.column_edges}
        revenue = by_target["urn:emc:column:snowflake:snowflake.sales.total_revenue"]
        assert revenue.source_urn == "urn:emc:column:sap:sap.orders.amount"
        assert revenue.transformation == "SUM(amount)"

        # A plain column reference is not a transformation.
        passthrough = by_target["urn:emc:column:snowflake:snowflake.sales.customer_id"]
        assert passthrough.transformation is None

    def test_transformation_keeps_source_dialect(self, parser: SqlLineageParser) -> None:
        """Rendering in another dialect would misrepresent the pipeline's actual code."""
        out = parser.parse(
            _artifact(
                "INSERT INTO snowflake.sales (order_month) "
                "SELECT DATE_TRUNC('month', order_date) AS order_month FROM sap.orders",
                platform="snowflake",
                dialect="snowflake",
            )
        )
        assert out.column_edges[0].transformation == "DATE_TRUNC('MONTH', order_date)"


class TestCreateTableAsSelect:
    def test_ctas_uses_projection_aliases_as_targets(self, parser: SqlLineageParser) -> None:
        out = parser.parse(
            _artifact(
                "CREATE TABLE databricks.customer_transform AS "
                "SELECT customer_id, customer_name FROM sap.customer",
                platform="databricks",
                dialect="spark",
            )
        )
        targets = {edge.target_urn for edge in out.column_edges}
        assert targets == {
            "urn:emc:column:databricks:databricks.customer_transform.customer_id",
            "urn:emc:column:databricks:databricks.customer_transform.customer_name",
        }


class TestPlatformInference:
    def test_leading_segment_matching_a_platform_wins(self, parser: SqlLineageParser) -> None:
        """`sap.orders` belongs to SAP even though the statement runs on Snowflake."""
        out = parser.parse(
            _artifact(
                "INSERT INTO snowflake.sales (customer_id) SELECT customer_id FROM sap.orders",
                platform="snowflake",
                dialect="snowflake",
            )
        )
        edge = out.table_edges[0]
        assert edge.source_urn.startswith("urn:emc:table:sap:")
        assert edge.target_urn.startswith("urn:emc:table:snowflake:")


class TestAmbiguityHandling:
    """The parser must degrade to table-level lineage rather than invent column edges."""

    def test_select_star_warns_and_skips_column_lineage(self, parser: SqlLineageParser) -> None:
        out = parser.parse(_artifact("CREATE VIEW analytics.v AS SELECT * FROM sap.customer"))
        assert out.table_edges
        assert out.column_edges == []
        assert any("SELECT *" in warning for warning in out.warnings)

    def test_unqualified_column_across_a_join_is_not_guessed(
        self, parser: SqlLineageParser
    ) -> None:
        out = parser.parse(
            _artifact(
                "INSERT INTO mart.x (a) SELECT customer_id FROM sap.customer "
                "JOIN sap.orders ON sap.orders.customer_id = sap.customer.customer_id"
            )
        )
        assert out.column_edges == []
        assert any("Could not resolve source table" in warning for warning in out.warnings)

    def test_unparseable_sql_is_reported_not_raised(self, parser: SqlLineageParser) -> None:
        out = parser.parse(_artifact("SELEKT ***"))
        assert out.statements_parsed == 0
        assert out.table_edges == []
        assert len(out.warnings) == 1

    def test_select_without_target_produces_nothing(self, parser: SqlLineageParser) -> None:
        out = parser.parse(_artifact("SELECT customer_id FROM sap.customer"))
        assert out.all_edges == []


class TestExtractorProtocol:
    def test_extract_returns_flat_edge_list(self, parser: SqlLineageParser) -> None:
        artifact = _artifact(
            "INSERT INTO mart.x (a) SELECT customer_id FROM sap.customer",
            pipeline_urn="urn:emc:pipeline:databricks:databricks.customer_etl",
            job_run_id="run-42",
        )
        edges = parser.extract(artifact)
        assert len(edges) == 2  # one table edge + one column edge
        assert all(edge.pipeline_urn is not None for edge in edges)
        assert all(edge.job_run_id == "run-42" for edge in edges)
        assert all(edge.evidence["sql"] for edge in edges)
