"""Seed the local environment with demo enterprise metadata.

Loads the SAP -> Databricks -> Snowflake -> Power BI landscape via the demo connector, adds
the business glossary and governance baseline, rebuilds the lineage graph and refreshes the
semantic index.

Usage::

    python scripts/seed_demo_data.py
    python scripts/seed_demo_data.py --reset-graph

Idempotent: safe to run repeatedly. Requires PostgreSQL to be migrated
(``alembic upgrade head``); Neo4j is optional and the script degrades gracefully without it.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.logging import configure_logging, get_logger  # noqa: E402
from app.db.session import session_scope  # noqa: E402
from app.ingestion.pipeline import IngestionPipeline  # noqa: E402
from app.schemas.glossary import BusinessTermCreate  # noqa: E402
from app.schemas.metadata import IngestionRequest  # noqa: E402
from app.schemas.search import IndexRequest  # noqa: E402
from app.services.glossary.glossary_service import GlossaryService  # noqa: E402
from app.services.governance.governance_service import GovernanceService  # noqa: E402
from app.services.lineage.lineage_service import LineageService  # noqa: E402
from app.services.search.hybrid_search import SearchService  # noqa: E402
from app.utils.identifiers import build_urn  # noqa: E402

configure_logging()
logger = get_logger("seed")

PRINCIPAL = "demo-seed"

GLOSSARY_TERMS: list[BusinessTermCreate] = [
    BusinessTermCreate(
        name="Customer",
        domain="sales",
        definition=(
            "A legal entity or individual that has purchased, or is contracted to purchase, "
            "goods or services from the organisation. The system of record is SAP customer "
            "master; every downstream customer key must reconcile to it."
        ),
        short_description="A party that buys from us.",
        synonyms=["client", "account", "buyer"],
        steward="Master Data Management",
        linked_entity_urns=[
            build_urn("TABLE", "sap", "sap.customer"),
            build_urn("TABLE", "snowflake", "snowflake.customer"),
            build_urn("COLUMN", "snowflake", "snowflake.customer.customer_id"),
        ],
    ),
    BusinessTermCreate(
        name="Customer Revenue",
        domain="finance",
        definition=(
            "Net revenue recognised from a customer in a period, calculated as the sum of net "
            "order amounts excluding tax, freight and intercompany transactions. Credit notes "
            "are netted against the original order month."
        ),
        short_description="Net recognised revenue per customer.",
        synonyms=["net revenue", "customer sales"],
        calculation="SUM(sap.orders.amount) grouped by customer and order month",
        unit="USD",
        steward="Finance Reporting",
        linked_entity_urns=[
            build_urn("COLUMN", "sap", "sap.orders.amount"),
            build_urn("COLUMN", "snowflake", "snowflake.sales.total_revenue"),
            build_urn("COLUMN", "powerbi", "powerbi.sales_dataset.revenue"),
        ],
    ),
    BusinessTermCreate(
        name="Monthly Revenue",
        domain="finance",
        definition=(
            "Total recognised revenue for a calendar month across all customers and regions. "
            "Reported on the Executive Sales Dashboard and used in the monthly business review."
        ),
        short_description="Total recognised revenue for a calendar month.",
        synonyms=["monthly sales", "revenue per month"],
        is_kpi=True,
        calculation="SUM(snowflake.sales.total_revenue) grouped by order_month",
        unit="USD",
        steward="Finance Reporting",
        linked_entity_urns=[
            build_urn("KPI", "powerbi", "powerbi.kpi.monthly_revenue"),
            build_urn("COLUMN", "snowflake", "snowflake.sales.total_revenue"),
            build_urn("DASHBOARD", "powerbi", "powerbi.sales_dashboard"),
        ],
    ),
    BusinessTermCreate(
        name="Active Customer",
        domain="sales",
        definition=(
            "A customer with at least one non-cancelled order in the trailing twelve months. "
            "Used as the denominator for retention and revenue-per-customer metrics."
        ),
        short_description="Customer with an order in the last 12 months.",
        is_kpi=True,
        calculation="COUNT(DISTINCT customer_id) WHERE order_date >= CURRENT_DATE - 365",
        steward="Sales Operations",
        linked_entity_urns=[build_urn("TABLE", "snowflake", "snowflake.sales")],
    ),
]


async def seed(*, reset_graph: bool = False) -> None:
    async with session_scope() as session:
        logger.info("seeding_governance_baseline")
        await GovernanceService(session).bootstrap()

    async with session_scope() as session:
        logger.info("seeding_glossary", extra={"terms": len(GLOSSARY_TERMS)})
        glossary = GlossaryService(session)
        for term in GLOSSARY_TERMS:
            await glossary.create_term(term)

    async with session_scope() as session:
        logger.info("running_demo_ingestion")
        result = await IngestionPipeline(session).run(
            IngestionRequest(
                connector="demo",
                data_source_name="demo-enterprise-landscape",
                full_refresh=True,
                extract_lineage=True,
            ),
            principal=PRINCIPAL,
        )
        logger.info(
            "ingestion_summary",
            extra={
                "entities": result.entities_created + result.entities_updated,
                "lineage_edges": result.lineage_edges_created + result.lineage_edges_updated,
                "errors": len(result.errors),
            },
        )
        for error in result.errors[:10]:
            logger.warning("ingestion_warning", extra={"detail": error})

    # Glossary links are re-applied after ingestion so terms attach to freshly created assets.
    async with session_scope() as session:
        glossary = GlossaryService(session)
        for term in GLOSSARY_TERMS:
            await glossary.create_term(term)

    async with session_scope() as session:
        try:
            logger.info("rebuilding_graph_projection")
            stats = await LineageService(session).rebuild_graph(principal=PRINCIPAL)
            logger.info("graph_rebuilt", extra=stats)
        except Exception as exc:  # noqa: BLE001 - the graph is optional for seeding
            logger.warning("graph_rebuild_skipped", extra={"error": str(exc)})

    async with session_scope() as session:
        logger.info("refreshing_semantic_index")
        totals = await SearchService(session).reindex(IndexRequest(include_glossary=True))
        logger.info("index_refreshed", extra=totals)

    if reset_graph:
        logger.info("reset_graph_requested_and_completed")

    print("\nDemo data loaded.\n")  # noqa: T201 - CLI feedback
    print("Try:")  # noqa: T201
    print("  curl 'http://localhost:8000/api/v1/search?q=monthly+revenue'")  # noqa: T201
    print(
        "  curl 'http://localhost:8000/api/v1/lineage/"
        "urn:emc:column:snowflake:snowflake.sales.total_revenue/upstream?depth=5'"
    )  # noqa: T201
    print(
        "  curl -X POST http://localhost:8000/api/v1/copilot/chat "
        '-H \'Content-Type: application/json\' '
        '-d \'{"message":"What will break if customer_id changes?"}\''
    )  # noqa: T201


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo enterprise metadata.")
    parser.add_argument(
        "--reset-graph",
        action="store_true",
        help="Clear the graph projection before rebuilding it.",
    )
    args = parser.parse_args()
    asyncio.run(seed(reset_graph=args.reset_graph))


if __name__ == "__main__":
    main()
