"""OpenLineage event connector.

Consumes OpenLineage run events (the emerging standard emitted by Airflow, Spark, dbt and
Flink) and maps them onto catalog entities and lineage edges. Events can be supplied inline
or from a directory of JSON files; an HTTP receiver endpoint is a later milestone.

Mapping
-------
``job``                       -> ``PIPELINE`` entity
``inputs[]``                  -> ``TABLE`` entity + ``READS_FROM`` edge (input -> job)
``outputs[]``                 -> ``TABLE`` entity + ``WRITES_TO`` edge (job -> output)
``schema`` facet              -> ``COLUMN`` entities
``columnLineage`` facet       -> column-level ``DERIVED_FROM`` edges with transformations
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterable
from pathlib import Path
from typing import Any

from app.connectors.base import (
    ConnectorCapabilities,
    MetadataConnector,
    RawEntity,
    RawLineage,
)
from app.core.constants import (
    EntityType,
    LineageLevel,
    LineageMethod,
    PlatformType,
    RelationshipType,
)
from app.core.logging import get_logger
from app.utils.identifiers import build_urn
from app.utils.timestamps import parse_timestamp, utcnow

logger = get_logger(__name__)


def _platform_from_namespace(namespace: str) -> str:
    """``snowflake://acme.eu-west-1`` -> ``snowflake``; ``postgres`` -> ``postgres``."""
    return (namespace.split("://", 1)[0] or PlatformType.OPENLINEAGE.value).lower()


class OpenLineageConnector(MetadataConnector):
    """Ingests OpenLineage run events.

    Config:
        ``events``: list of event dicts.
        ``events_directory``: directory of ``*.json`` event files.
    """

    name = "openlineage"
    platform = PlatformType.OPENLINEAGE
    description = "Ingests OpenLineage run events from Airflow, Spark, dbt and similar tools."
    capabilities = ConnectorCapabilities(
        supports_lineage=True, supports_column_lineage=True, supports_incremental=True
    )
    required_config = ()

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)

    # ------------------------------------------------------------------ #
    # Event loading
    # ------------------------------------------------------------------ #
    def _events(self) -> Iterable[dict[str, Any]]:
        yield from (self.config.get("events") or [])

        directory = self.config.get("events_directory")
        if not directory:
            return
        root = Path(directory)
        if not root.is_dir():
            logger.warning("openlineage_directory_missing", extra={"path": str(directory)})
            return
        for path in sorted(root.rglob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(
                    "openlineage_event_unreadable", extra={"path": str(path), "error": str(exc)}
                )
                continue
            if isinstance(payload, list):
                yield from payload
            else:
                yield payload

    async def test_connection(self) -> tuple[bool, str]:
        count = sum(1 for _ in self._events())
        return count > 0, f"{count} OpenLineage event(s) available."

    # ------------------------------------------------------------------ #
    # Extraction
    # ------------------------------------------------------------------ #
    async def extract_entities(self) -> AsyncIterator[RawEntity]:
        seen: set[str] = set()
        for event in self._events():
            job = event.get("job") or {}
            job_platform = _platform_from_namespace(str(job.get("namespace", "openlineage")))
            job_name = str(job.get("name", ""))
            if job_name and job_name not in seen:
                seen.add(job_name)
                yield RawEntity(
                    entity_type=EntityType.PIPELINE,
                    name=job_name.split(".")[-1],
                    qualified_name=job_name,
                    platform=job_platform,
                    description=(event.get("job", {}).get("facets", {}) or {})
                    .get("documentation", {})
                    .get("description"),
                    properties={"namespace": job.get("namespace")},
                )

            for dataset in list(event.get("inputs") or []) + list(event.get("outputs") or []):
                name = str(dataset.get("name", ""))
                if not name or name in seen:
                    continue
                seen.add(name)
                platform = _platform_from_namespace(str(dataset.get("namespace", "")))
                yield RawEntity(
                    entity_type=EntityType.TABLE,
                    name=name.split(".")[-1],
                    qualified_name=name,
                    platform=platform,
                    properties={"namespace": dataset.get("namespace")},
                )
                fields = (
                    (dataset.get("facets") or {}).get("schema", {}).get("fields", [])
                )
                for index, field in enumerate(fields):
                    field_name = str(field.get("name", ""))
                    if not field_name:
                        continue
                    yield RawEntity(
                        entity_type=EntityType.COLUMN,
                        name=field_name,
                        qualified_name=f"{name}.{field_name}",
                        platform=platform,
                        parent_qualified_name=name,
                        parent_entity_type=EntityType.TABLE,
                        data_type=field.get("type"),
                        description=field.get("description"),
                        ordinal_position=index + 1,
                    )

    async def extract_lineage(self) -> AsyncIterator[RawLineage]:
        for event in self._events():
            job = event.get("job") or {}
            job_name = str(job.get("name", ""))
            job_platform = _platform_from_namespace(str(job.get("namespace", "openlineage")))
            run_id = str((event.get("run") or {}).get("runId", "")) or None
            observed_at = parse_timestamp(event.get("eventTime")) or utcnow()
            pipeline_urn = (
                build_urn(EntityType.PIPELINE, job_platform, job_name) if job_name else None
            )

            for dataset in event.get("inputs") or []:
                if pipeline_urn is None:
                    continue
                yield RawLineage(
                    source_urn=self._dataset_urn(dataset),
                    target_urn=pipeline_urn,
                    relationship=RelationshipType.READS_FROM,
                    level=LineageLevel.TABLE,
                    method=LineageMethod.OPENLINEAGE,
                    pipeline_urn=pipeline_urn,
                    job_run_id=run_id,
                    observed_at=observed_at,
                    evidence={"source": "openlineage", "event_type": event.get("eventType")},
                )

            for dataset in event.get("outputs") or []:
                dataset_urn = self._dataset_urn(dataset)
                if pipeline_urn is not None:
                    yield RawLineage(
                        source_urn=pipeline_urn,
                        target_urn=dataset_urn,
                        relationship=RelationshipType.WRITES_TO,
                        level=LineageLevel.TABLE,
                        method=LineageMethod.OPENLINEAGE,
                        pipeline_urn=pipeline_urn,
                        job_run_id=run_id,
                        observed_at=observed_at,
                        evidence={"source": "openlineage", "event_type": event.get("eventType")},
                    )
                for edge in self._column_lineage(dataset, pipeline_urn, run_id, observed_at):
                    yield edge

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _dataset_urn(dataset: dict[str, Any]) -> str:
        platform = _platform_from_namespace(str(dataset.get("namespace", "")))
        return build_urn(EntityType.TABLE, platform, str(dataset.get("name", "")))

    def _column_lineage(
        self,
        dataset: dict[str, Any],
        pipeline_urn: str | None,
        run_id: str | None,
        observed_at: Any,
    ) -> list[RawLineage]:
        facet = (dataset.get("facets") or {}).get("columnLineage") or {}
        fields: dict[str, Any] = facet.get("fields") or {}
        output_platform = _platform_from_namespace(str(dataset.get("namespace", "")))
        output_name = str(dataset.get("name", ""))

        edges: list[RawLineage] = []
        for output_field, spec in fields.items():
            target_urn = build_urn(
                EntityType.COLUMN, output_platform, f"{output_name}.{output_field}"
            )
            transformation = spec.get("transformationDescription")
            for input_field in spec.get("inputFields") or []:
                input_platform = _platform_from_namespace(str(input_field.get("namespace", "")))
                source_urn = build_urn(
                    EntityType.COLUMN,
                    input_platform,
                    f"{input_field.get('name', '')}.{input_field.get('field', '')}",
                )
                edges.append(
                    RawLineage(
                        source_urn=source_urn,
                        target_urn=target_urn,
                        relationship=RelationshipType.DERIVED_FROM,
                        level=LineageLevel.COLUMN,
                        method=LineageMethod.OPENLINEAGE,
                        transformation=transformation,
                        pipeline_urn=pipeline_urn,
                        job_run_id=run_id,
                        observed_at=observed_at,
                        evidence={"source": "openlineage.columnLineage"},
                    )
                )
        return edges
