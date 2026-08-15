"""Generic SQL connector.

Ingests lineage from a set of SQL scripts (dbt models, ELT steps, migration files) without
connecting to a live database. Useful when only the transformation code is available.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from app.connectors.base import (
    ConnectorCapabilities,
    MetadataConnector,
    RawEntity,
    SqlArtifact,
)
from app.core.constants import PlatformType
from app.core.exceptions import ConnectorError
from app.core.logging import get_logger

logger = get_logger(__name__)


class GenericSQLConnector(MetadataConnector):
    """Reads ``*.sql`` files and hands them to the lineage parser.

    Config:
        ``sql_directory``: folder containing SQL files (recursively scanned).
        ``sql_statements``: inline list of statements (takes precedence).
        ``dialect``: SQLGlot dialect name, defaults to ``ansi``.
        ``platform``: platform label applied to discovered assets.
    """

    name = "generic_sql"
    platform = PlatformType.GENERIC_SQL
    description = "Extracts lineage from SQL files or inline statements."
    capabilities = ConnectorCapabilities(supports_lineage=True, supports_column_lineage=True)
    required_config = ()

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._dialect = str(self.config.get("dialect", "ansi"))
        self._platform_label = str(self.config.get("platform", PlatformType.GENERIC_SQL.value))

    async def test_connection(self) -> tuple[bool, str]:
        statements = self.config.get("sql_statements") or []
        directory = self.config.get("sql_directory")
        if statements:
            return True, f"{len(statements)} inline statement(s) configured."
        if directory and Path(directory).is_dir():
            count = len(list(Path(directory).rglob("*.sql")))
            return True, f"{count} SQL file(s) found in {directory}."
        return False, "Configure either 'sql_statements' or an existing 'sql_directory'."

    async def extract_entities(self) -> AsyncIterator[RawEntity]:
        """Assets are discovered from the parsed SQL, so nothing is emitted here.

        The ingestion pipeline creates placeholder entities for tables and columns referenced
        by lineage that are not yet in the catalog.
        """
        return
        yield  # pragma: no cover

    async def extract_sql(self) -> AsyncIterator[SqlArtifact]:
        for index, statement in enumerate(self.config.get("sql_statements") or []):
            yield SqlArtifact(
                sql=str(statement),
                platform=self._platform_label,
                dialect=self._dialect,
                default_database=self.config.get("database"),
                default_schema=self.config.get("schema"),
                source=f"inline:{index}",
            )

        directory = self.config.get("sql_directory")
        if not directory:
            return
        root = Path(directory)
        if not root.is_dir():
            raise ConnectorError(f"sql_directory '{directory}' does not exist.")
        for path in sorted(root.rglob("*.sql")):
            try:
                sql = path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("sql_file_unreadable", extra={"path": str(path), "error": str(exc)})
                continue
            yield SqlArtifact(
                sql=sql,
                platform=self._platform_label,
                dialect=self._dialect,
                default_database=self.config.get("database"),
                default_schema=self.config.get("schema"),
                source=str(path),
            )
