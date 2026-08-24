"""PostgreSQL metadata connector.

Reads technical metadata from ``information_schema`` using the application's async engine
factory. Credentials come from the connector configuration (or a secret reference), never
from source code.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.connectors.base import (
    ConnectorCapabilities,
    MetadataConnector,
    RawEntity,
    RawLineage,
    SqlArtifact,
)
from app.core.constants import EntityType, PlatformType, RelationshipType
from app.core.exceptions import ConnectorError
from app.core.logging import get_logger

logger = get_logger(__name__)

_TABLES_SQL = text(
    """
    SELECT table_schema, table_name, table_type
    FROM information_schema.tables
    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
      AND (:schema_filter IS NULL OR table_schema = :schema_filter)
    ORDER BY table_schema, table_name
    """
)

_COLUMNS_SQL = text(
    """
    SELECT table_schema, table_name, column_name, data_type,
           is_nullable, ordinal_position, col_description(
               format('%I.%I', table_schema, table_name)::regclass::oid, ordinal_position
           ) AS column_comment
    FROM information_schema.columns
    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
      AND (:schema_filter IS NULL OR table_schema = :schema_filter)
    ORDER BY table_schema, table_name, ordinal_position
    """
)

_VIEWS_SQL = text(
    """
    SELECT table_schema, table_name, view_definition
    FROM information_schema.views
    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
      AND (:schema_filter IS NULL OR table_schema = :schema_filter)
    """
)

_CONSTRAINTS_SQL = text(
    """
    SELECT
        tc.table_schema,
        tc.table_name,
        tc.constraint_name,
        tc.constraint_type,
        array_agg(kcu.column_name ORDER BY kcu.ordinal_position) AS column_names
    FROM information_schema.table_constraints tc
    LEFT JOIN information_schema.key_column_usage kcu
        ON tc.constraint_name = kcu.constraint_name
       AND tc.table_schema = kcu.table_schema
       AND tc.table_name = kcu.table_name
    WHERE tc.table_schema NOT IN ('pg_catalog', 'information_schema')
      AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
      AND (:schema_filter IS NULL OR tc.table_schema = :schema_filter)
    GROUP BY tc.table_schema, tc.table_name, tc.constraint_name, tc.constraint_type
    ORDER BY tc.table_schema, tc.table_name, tc.constraint_name
    """
)


class PostgresConnector(MetadataConnector):
    """Extracts databases, schemas, tables, views and columns from PostgreSQL."""

    name = "postgres"
    platform = PlatformType.POSTGRES
    description = "PostgreSQL technical metadata via information_schema."
    capabilities = ConnectorCapabilities(
        supports_lineage=True, supports_column_lineage=True, supports_incremental=True
    )
    required_config = ("dsn",)

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._engine: AsyncEngine | None = None

    def _dsn(self) -> str:
        dsn = str(self.config.get("dsn", ""))
        if not dsn:
            raise ConnectorError("PostgresConnector requires a 'dsn' configuration value.")
        return dsn.replace("postgresql://", "postgresql+asyncpg://", 1)

    def _get_engine(self) -> AsyncEngine:
        if self._engine is None:
            self._engine = create_async_engine(self._dsn(), pool_pre_ping=True)
        return self._engine

    async def test_connection(self) -> tuple[bool, str]:
        try:
            async with self._get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True, "Connection successful."
        except Exception as exc:
            return False, str(exc)

    async def extract_entities(self) -> AsyncIterator[RawEntity]:
        database = str(self.config.get("database", "postgres"))
        schema_filter = self.config.get("schema")

        try:
            async with self._get_engine().connect() as conn:
                constraints_by_table: dict[tuple[str, str], list[dict[str, object]]] = {}
                for schema, table, constraint_name, constraint_type, column_names in (
                    await conn.execute(_CONSTRAINTS_SQL, {"schema_filter": schema_filter})
                ).all():
                    constraints_by_table.setdefault((schema, table), []).append(
                        {
                            "name": constraint_name,
                            "type": constraint_type,
                            "columns": list(column_names or []),
                        }
                    )

                yield RawEntity(
                    entity_type=EntityType.DATABASE,
                    name=database,
                    qualified_name=database,
                    platform=self.platform.value,
                )

                seen_schemas: set[str] = set()
                tables = (await conn.execute(_TABLES_SQL, {"schema_filter": schema_filter})).all()
                for schema, table, table_type in tables:
                    if schema not in seen_schemas:
                        seen_schemas.add(schema)
                        yield RawEntity(
                            entity_type=EntityType.SCHEMA,
                            name=schema,
                            qualified_name=f"{database}.{schema}",
                            parent_qualified_name=database,
                            parent_entity_type=EntityType.DATABASE,
                            platform=self.platform.value,
                        )
                    yield RawEntity(
                        entity_type=(EntityType.VIEW if table_type == "VIEW" else EntityType.TABLE),
                        name=table,
                        qualified_name=f"{database}.{schema}.{table}",
                        parent_qualified_name=f"{database}.{schema}",
                        parent_entity_type=EntityType.SCHEMA,
                        platform=self.platform.value,
                        properties={
                            "table_type": table_type,
                            "constraints": constraints_by_table.get((schema, table), []),
                        },
                        constraints=constraints_by_table.get((schema, table), []),
                    )

                columns = (await conn.execute(_COLUMNS_SQL, {"schema_filter": schema_filter})).all()
                for schema, table, column, data_type, nullable, position, comment in columns:
                    yield RawEntity(
                        entity_type=EntityType.COLUMN,
                        name=column,
                        qualified_name=f"{database}.{schema}.{table}.{column}",
                        parent_qualified_name=f"{database}.{schema}.{table}",
                        parent_entity_type=EntityType.TABLE,
                        platform=self.platform.value,
                        description=comment,
                        data_type=data_type,
                        is_nullable=(nullable == "YES"),
                        ordinal_position=position,
                        properties={
                            "constraints": [
                                constraint
                                for constraint in constraints_by_table.get((schema, table), [])
                                if column in (constraint.get("columns") or [])
                            ]
                        },
                    )
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorError(f"PostgreSQL metadata extraction failed: {exc}") from exc

    async def extract_sql(self) -> AsyncIterator[SqlArtifact]:
        """View definitions are the cheapest reliable source of lineage in PostgreSQL."""
        database = str(self.config.get("database", "postgres"))
        schema_filter = self.config.get("schema")
        async with self._get_engine().connect() as conn:
            for schema, view, definition in (
                await conn.execute(_VIEWS_SQL, {"schema_filter": schema_filter})
            ).all():
                if not definition:
                    continue
                yield SqlArtifact(
                    sql=f"CREATE VIEW {database}.{schema}.{view} AS {definition}",
                    platform=self.platform.value,
                    dialect="postgres",
                    default_database=database,
                    default_schema=schema,
                    source=f"information_schema.views:{schema}.{view}",
                )

    async def extract_lineage(self) -> AsyncIterator[RawLineage]:
        """Foreign keys as ``REFERENCES`` relationships.

        TODO: emit FK-based ``REFERENCES`` edges; view lineage already flows through
        ``extract_sql`` and the SQL parser.
        """
        return
        yield RawLineage(source_urn="", target_urn="", relationship=RelationshipType.REFERENCES)

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
