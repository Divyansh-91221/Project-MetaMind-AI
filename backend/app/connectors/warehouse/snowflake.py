"""Snowflake connector (skeleton).

The extraction contract is fully defined; the transport is left for the milestone that adds
the ``snowflake-connector-python`` dependency. Keeping the class registered means the UI can
already list it and report that it is not yet implemented.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.connectors.base import (
    ConnectorCapabilities,
    MetadataConnector,
    RawEntity,
    RawLineage,
    SqlArtifact,
)
from app.core.constants import PlatformType
from app.core.exceptions import ConnectorError

# Reference queries for the implementation milestone.
ACCOUNT_USAGE_TABLES = """
SELECT table_catalog, table_schema, table_name, row_count, comment
FROM snowflake.account_usage.tables
WHERE deleted IS NULL
"""

ACCOUNT_USAGE_COLUMNS = """
SELECT table_catalog, table_schema, table_name, column_name,
       data_type, is_nullable, ordinal_position, comment
FROM snowflake.account_usage.columns
WHERE deleted IS NULL
"""

ACCESS_HISTORY_LINEAGE = """
SELECT query_id, objects_modified, base_objects_accessed, query_start_time
FROM snowflake.account_usage.access_history
WHERE query_start_time >= DATEADD('day', -:lookback_days, CURRENT_TIMESTAMP())
"""


class SnowflakeConnector(MetadataConnector):
    """Extracts warehouse metadata and query-history lineage from Snowflake."""

    name = "snowflake"
    platform = PlatformType.SNOWFLAKE
    description = "Snowflake technical metadata and ACCESS_HISTORY lineage."
    capabilities = ConnectorCapabilities(
        supports_lineage=True,
        supports_column_lineage=True,
        supports_quality=True,
        supports_incremental=True,
        implemented=False,
    )
    required_config = ("account", "user", "warehouse", "database")

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)

    async def test_connection(self) -> tuple[bool, str]:
        missing = self.validate_config()
        if missing:
            return False, f"Missing configuration: {', '.join(missing)}"
        return False, "Snowflake connector is not implemented yet."

    async def extract_entities(self) -> AsyncIterator[RawEntity]:
        # TODO: query ACCOUNT_USAGE_TABLES / ACCOUNT_USAGE_COLUMNS and map to RawEntity.
        raise ConnectorError(
            "Snowflake connector is not implemented yet.",
            details={"planned_queries": ["ACCOUNT_USAGE.TABLES", "ACCOUNT_USAGE.COLUMNS"]},
        )
        yield  # pragma: no cover

    async def extract_sql(self) -> AsyncIterator[SqlArtifact]:
        # TODO: emit view definitions from INFORMATION_SCHEMA.VIEWS for SQL-parsed lineage.
        return
        yield  # pragma: no cover

    async def extract_lineage(self) -> AsyncIterator[RawLineage]:
        # TODO: map ACCESS_HISTORY objects_modified/base_objects_accessed to column lineage.
        return
        yield  # pragma: no cover
