"""Connector interfaces.

Connectors are pluggable and must stay decoupled from services: they emit *raw* records and
know nothing about the database, the graph or the agent. The ingestion layer normalises,
resolves and persists whatever a connector yields.

Two extension points live here:

``MetadataConnector``
    Pulls technical metadata (and optionally declared lineage / quality) from a source system.
``LineageExtractor``
    Derives lineage from an artefact such as a SQL statement or an OpenLineage event.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

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


@dataclass(slots=True)
class ConnectorCapabilities:
    """Declares what a connector can do so the UI and pipeline can adapt."""

    supports_lineage: bool = False
    supports_column_lineage: bool = False
    supports_quality: bool = False
    supports_incremental: bool = False
    implemented: bool = True


@dataclass(slots=True)
class RawEntity:
    """A metadata record exactly as the source system describes it."""

    entity_type: EntityType
    name: str
    qualified_name: str
    platform: str
    parent_qualified_name: str | None = None
    parent_entity_type: EntityType | None = None
    display_name: str | None = None
    description: str | None = None
    data_type: str | None = None
    ordinal_position: int | None = None
    is_nullable: bool | None = None
    is_primary_key: bool | None = None
    row_count: int | None = None
    tags: list[str] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)
    owners: list[tuple[str, str]] = field(default_factory=list)
    """``(owner_name, role)`` pairs."""
    classifications: list[str] = field(default_factory=list)
    business_terms: list[str] = field(default_factory=list)

    @property
    def urn(self) -> str:
        return build_urn(self.entity_type, self.platform, self.qualified_name)

    @property
    def parent_urn(self) -> str | None:
        if not self.parent_qualified_name or self.parent_entity_type is None:
            return None
        return build_urn(self.parent_entity_type, self.platform, self.parent_qualified_name)


@dataclass(slots=True)
class RawLineage:
    """A lineage assertion emitted by a connector or extractor.

    ``confidence`` is optional: when omitted, the confidence scorer derives it from ``method``
    and the available evidence. Connectors must never fabricate high confidence.
    """

    source_urn: str
    target_urn: str
    relationship: RelationshipType = RelationshipType.DERIVED_FROM
    level: LineageLevel = LineageLevel.TABLE
    method: LineageMethod = LineageMethod.CONNECTOR_DECLARED
    transformation: str | None = None
    pipeline_urn: str | None = None
    job_run_id: str | None = None
    confidence: float | None = None
    observed_at: datetime | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RawQualityMetric:
    """A quality or freshness measurement reported by a source system."""

    entity_urn: str
    dimension: QualityDimension
    metric_name: str
    value: float | None = None
    unit: str | None = None
    threshold: float | None = None
    status: QualityStatus = QualityStatus.UNKNOWN
    measured_at: datetime | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SqlArtifact:
    """A SQL statement (view definition, ETL step) to be parsed for lineage.

    Connectors expose SQL rather than parsing it themselves - parsing belongs to the lineage
    service, which keeps connectors free of business logic.
    """

    sql: str
    platform: str
    dialect: str = "ansi"
    default_database: str | None = None
    default_schema: str | None = None
    pipeline_urn: str | None = None
    job_run_id: str | None = None
    source: str = ""


class MetadataConnector(abc.ABC):
    """Base class every connector implements.

    Implementations must be stateless between runs, must not hold open connections across
    ingestion runs, and must resolve credentials from configuration - never hardcode them.
    """

    name: str = "base"
    platform: PlatformType = PlatformType.UNKNOWN
    description: str = ""
    capabilities: ConnectorCapabilities = ConnectorCapabilities()
    required_config: Sequence[str] = ()

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    def validate_config(self) -> list[str]:
        """Return the list of missing required configuration keys."""
        return [key for key in self.required_config if not self.config.get(key)]

    @abc.abstractmethod
    async def test_connection(self) -> tuple[bool, str]:
        """Return ``(success, message)`` without mutating anything."""

    @abc.abstractmethod
    def extract_entities(self) -> AsyncIterator[RawEntity]:
        """Yield catalog objects. Implemented as an ``async def`` generator."""

    async def extract_lineage(self) -> AsyncIterator[RawLineage]:
        """Yield declared lineage. Default: none."""
        return
        yield  # pragma: no cover - makes this an async generator

    async def extract_quality(self) -> AsyncIterator[RawQualityMetric]:
        """Yield quality/freshness metrics. Default: none."""
        return
        yield  # pragma: no cover

    async def extract_sql(self) -> AsyncIterator[SqlArtifact]:
        """Yield SQL the lineage service should parse. Default: none."""
        return
        yield  # pragma: no cover

    async def close(self) -> None:
        """Release any resources opened during extraction."""
        return None


@runtime_checkable
class LineageExtractor(Protocol):
    """Derives lineage from an artefact (SQL text, pipeline definition, run event)."""

    method: LineageMethod

    def extract(self, artifact: Any, **context: Any) -> list[RawLineage]:
        """Return the lineage assertions found in ``artifact``."""
        ...
