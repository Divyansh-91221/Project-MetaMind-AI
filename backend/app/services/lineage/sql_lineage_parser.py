"""SQL-based lineage extraction using SQLGlot.

This is the highest-trust automated extractor: it derives lineage from the transformation
code itself rather than from names or from an LLM. It resolves

* the write target of ``INSERT ... SELECT``, ``CREATE TABLE AS SELECT`` and ``CREATE VIEW``,
* every source table in the ``FROM``/``JOIN`` clauses,
* the column-level mapping between projections and their source columns,
* the transformation expression for each mapping (e.g. ``SUM(amount)``).

Unresolvable constructs (``SELECT *``, dynamic SQL) degrade to table-level lineage plus a
warning - they never produce guessed column edges.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from app.connectors.base import RawLineage, SqlArtifact
from app.core.constants import (
    EntityType,
    LineageLevel,
    LineageMethod,
    PlatformType,
    RelationshipType,
)
from app.core.logging import get_logger
from app.utils.identifiers import build_qualified_name, build_urn
from app.utils.timestamps import utcnow

logger = get_logger(__name__)

_KNOWN_PLATFORMS = {platform.value for platform in PlatformType}


@dataclass(slots=True)
class SqlLineageOutput:
    """Parser result: table edges, column edges and anything that could not be resolved."""

    table_edges: list[RawLineage] = field(default_factory=list)
    column_edges: list[RawLineage] = field(default_factory=list)
    statements_parsed: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def all_edges(self) -> list[RawLineage]:
        return [*self.table_edges, *self.column_edges]


@dataclass(slots=True)
class _TableRef:
    """A resolved table reference."""

    qualified_name: str
    platform: str

    def urn(self, entity_type: EntityType = EntityType.TABLE) -> str:
        return build_urn(entity_type, self.platform, self.qualified_name)

    def column_urn(self, column: str) -> str:
        return build_urn(
            EntityType.COLUMN, self.platform, build_qualified_name(self.qualified_name, column)
        )


class SqlLineageParser:
    """Implements the :class:`~app.connectors.base.LineageExtractor` protocol."""

    method = LineageMethod.SQL_PARSE

    def extract(self, artifact: SqlArtifact, **_: object) -> list[RawLineage]:
        """Protocol entry point - returns a flat edge list."""
        return self.parse(artifact).all_edges

    def parse(self, artifact: SqlArtifact) -> SqlLineageOutput:
        """Parse every statement in the artifact."""
        output = SqlLineageOutput()
        dialect = _normalize_dialect(artifact.dialect)

        try:
            statements = sqlglot.parse(artifact.sql, read=dialect)
        except ParseError as exc:
            output.warnings.append(f"Could not parse SQL ({artifact.source or 'inline'}): {exc}")
            logger.warning("sql_parse_failed", extra={"source": artifact.source, "error": str(exc)})
            return output

        for statement in statements:
            if statement is None:
                continue
            output.statements_parsed += 1
            try:
                self._parse_statement(statement, artifact, output)
            except Exception as exc:  # noqa: BLE001 - one bad statement must not fail the run
                output.warnings.append(f"Statement skipped: {exc}")
                logger.warning(
                    "sql_statement_skipped",
                    extra={"source": artifact.source, "error": str(exc)},
                )
        return output

    # ------------------------------------------------------------------ #
    # Statement handling
    # ------------------------------------------------------------------ #
    def _parse_statement(
        self, statement: exp.Expression, artifact: SqlArtifact, output: SqlLineageOutput
    ) -> None:
        target, target_columns, select = _resolve_target(statement)
        if target is None or select is None:
            return

        target_ref = _table_ref(target, artifact)
        source_tables = _source_tables(select, artifact)
        if not source_tables:
            output.warnings.append(f"No source tables found for target {target_ref.qualified_name}.")
            return

        observed_at = utcnow()
        evidence = {
            "sql": artifact.sql.strip(),
            "source": artifact.source or "inline",
            "dialect": artifact.dialect,
        }

        # --- Table level ------------------------------------------------
        for alias, source_ref in source_tables.items():
            if source_ref.qualified_name == target_ref.qualified_name:
                continue
            output.table_edges.append(
                RawLineage(
                    source_urn=source_ref.urn(),
                    target_urn=target_ref.urn(),
                    relationship=RelationshipType.DERIVED_FROM,
                    level=LineageLevel.TABLE,
                    method=self.method,
                    pipeline_urn=artifact.pipeline_urn,
                    job_run_id=artifact.job_run_id,
                    observed_at=observed_at,
                    evidence={**evidence, "source_alias": alias},
                )
            )

        # --- Column level -----------------------------------------------
        projections = list(select.expressions)
        if any(isinstance(projection, exp.Star) for projection in projections):
            output.warnings.append(
                f"SELECT * against {target_ref.qualified_name}: column lineage requires a schema, "
                "only table-level lineage was produced."
            )
            return

        for index, projection in enumerate(projections):
            target_column = _target_column_name(projection, target_columns, index)
            if not target_column:
                continue
            transformation = _transformation(projection)

            for column in projection.find_all(exp.Column):
                source_ref = _resolve_column_table(column, source_tables)
                if source_ref is None:
                    output.warnings.append(
                        f"Could not resolve source table for column '{column.sql()}'."
                    )
                    continue
                output.column_edges.append(
                    RawLineage(
                        source_urn=source_ref.column_urn(column.name),
                        target_urn=target_ref.column_urn(target_column),
                        relationship=RelationshipType.DERIVED_FROM,
                        level=LineageLevel.COLUMN,
                        method=self.method,
                        transformation=transformation,
                        pipeline_urn=artifact.pipeline_urn,
                        job_run_id=artifact.job_run_id,
                        observed_at=observed_at,
                        evidence={**evidence, "projection": projection.sql()},
                    )
                )


# --------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------- #
def _normalize_dialect(dialect: str | None) -> str | None:
    """SQLGlot uses ``None`` for its permissive default dialect."""
    if not dialect or dialect.lower() in {"ansi", "sql", "generic", "default"}:
        return None
    return dialect.lower()


def _resolve_target(
    statement: exp.Expression,
) -> tuple[exp.Table | None, list[str], exp.Select | None]:
    """Return ``(target_table, explicit_target_columns, select_expression)``."""
    target: exp.Table | None = None
    columns: list[str] = []
    select: exp.Select | None = None

    if isinstance(statement, exp.Insert):
        schema_or_table = statement.this
        if isinstance(schema_or_table, exp.Schema):
            target = schema_or_table.this if isinstance(schema_or_table.this, exp.Table) else None
            columns = [column.name for column in schema_or_table.expressions]
        elif isinstance(schema_or_table, exp.Table):
            target = schema_or_table
        select = statement.expression if isinstance(statement.expression, exp.Select) else None

    elif isinstance(statement, exp.Create):
        schema_or_table = statement.this
        if isinstance(schema_or_table, exp.Schema):
            target = schema_or_table.this if isinstance(schema_or_table.this, exp.Table) else None
            columns = [
                column.name
                for column in schema_or_table.expressions
                if isinstance(column, exp.ColumnDef | exp.Identifier)
            ]
        elif isinstance(schema_or_table, exp.Table):
            target = schema_or_table
        select = statement.expression if isinstance(statement.expression, exp.Select) else None

    return target, columns, select


def _infer_platform(qualified_name: str, default_platform: str) -> str:
    """Heuristic: a leading segment matching a known platform wins.

    ``sap.orders`` -> ``sap``. Everything else falls back to the artifact's platform.

    TODO: replace with an explicit namespace-to-platform mapping stored per data source, so
    ``analytics.orders`` can be routed to the right system.
    """
    head = qualified_name.split(".", 1)[0].lower()
    return head if head in _KNOWN_PLATFORMS else default_platform


def _table_ref(table: exp.Table, artifact: SqlArtifact) -> _TableRef:
    parts = [
        table.catalog or None,
        table.db or artifact.default_schema,
        table.name,
    ]
    if not table.db and artifact.default_database and not table.catalog:
        parts[0] = artifact.default_database
    qualified_name = build_qualified_name(*parts)
    return _TableRef(
        qualified_name=qualified_name,
        platform=_infer_platform(qualified_name, artifact.platform),
    )


def _source_tables(select: exp.Select, artifact: SqlArtifact) -> dict[str, _TableRef]:
    """Map every alias (and bare table name) in the query to its resolved table."""
    refs: dict[str, _TableRef] = {}
    for table in select.find_all(exp.Table):
        ref = _table_ref(table, artifact)
        refs[table.alias_or_name.lower()] = ref
        refs.setdefault(table.name.lower(), ref)
        refs.setdefault(ref.qualified_name.lower(), ref)
    return refs


def _resolve_column_table(
    column: exp.Column, source_tables: dict[str, _TableRef]
) -> _TableRef | None:
    """Resolve which source table a column belongs to.

    An unqualified column is only resolved when there is exactly one source table - guessing
    across a join would fabricate lineage.
    """
    qualifier = (column.table or "").lower()
    if qualifier:
        return source_tables.get(qualifier)
    distinct = {ref.qualified_name: ref for ref in source_tables.values()}
    return next(iter(distinct.values())) if len(distinct) == 1 else None


def _target_column_name(
    projection: exp.Expression, target_columns: list[str], index: int
) -> str | None:
    """Explicit INSERT column list wins; otherwise use the projection alias/name."""
    if index < len(target_columns):
        return target_columns[index]
    name = projection.alias_or_name
    return name or None


def _transformation(projection: exp.Expression) -> str | None:
    """Return the SQL expression when the projection is more than a plain column reference."""
    inner = projection.this if isinstance(projection, exp.Alias) else projection
    if isinstance(inner, exp.Column):
        return None
    return inner.sql()
