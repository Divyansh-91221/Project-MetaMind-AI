"""Lineage API contracts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from app.core.constants import (
    Direction,
    EntityType,
    LineageLevel,
    LineageMethod,
    RelationshipType,
    VerificationStatus,
)
from app.schemas.common import APIModel


class LineageNode(APIModel):
    """A node in a lineage graph response."""

    urn: str
    id: uuid.UUID | None = None
    name: str
    qualified_name: str
    entity_type: EntityType
    platform: str
    description: str | None = None
    depth: int = 0
    properties: dict[str, Any] = Field(default_factory=dict)


class LineageEdgeRead(APIModel):
    """The canonical lineage relationship contract."""

    id: uuid.UUID | None = None
    source_urn: str
    target_urn: str
    relationship: RelationshipType = RelationshipType.DERIVED_FROM
    transformation: str | None = None
    pipeline_urn: str | None = None
    level: LineageLevel = LineageLevel.TABLE
    method: LineageMethod = LineageMethod.CONNECTOR_DECLARED
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    verified: bool = False
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    observed_at: datetime | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_inferred(self) -> bool:
        return self.method is LineageMethod.AI_INFERRED


class LineageEdgeCreate(APIModel):
    """Manual or connector-supplied lineage assertion."""

    source_urn: str
    target_urn: str
    relationship: RelationshipType = RelationshipType.DERIVED_FROM
    level: LineageLevel = LineageLevel.TABLE
    method: LineageMethod = LineageMethod.MANUAL
    transformation: str | None = None
    pipeline_urn: str | None = None
    job_run_id: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    observed_at: datetime | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _no_self_reference(self) -> LineageEdgeCreate:
        if self.source_urn == self.target_urn:
            raise ValueError("A lineage edge cannot point an entity at itself.")
        return self


class LineageGraph(APIModel):
    """Node/edge payload consumed directly by the UI lineage canvas."""

    root_urn: str
    direction: Direction
    depth: int
    nodes: list[LineageNode] = Field(default_factory=list)
    edges: list[LineageEdgeRead] = Field(default_factory=list)
    truncated: bool = Field(
        default=False, description="True when traversal hit the configured depth or size limit."
    )


class LineageQuery(APIModel):
    depth: int = Field(default=3, ge=1, le=15)
    level: LineageLevel | None = None
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    include_inferred: bool = True
    include_unverified: bool = True


class LineagePath(APIModel):
    """A concrete route between two assets, used as Copilot evidence."""

    source_urn: str
    target_urn: str
    hops: int
    nodes: list[LineageNode] = Field(default_factory=list)
    edges: list[LineageEdgeRead] = Field(default_factory=list)
    min_confidence: float = 1.0


class LineageVerificationRequest(APIModel):
    """Human validation of an (often AI-inferred) lineage edge."""

    status: VerificationStatus = VerificationStatus.VERIFIED
    note: str | None = None


class SqlLineageRequest(APIModel):
    """Extract lineage from a SQL statement without persisting it."""

    sql: str = Field(min_length=1)
    dialect: str = "ansi"
    default_platform: str = "generic_sql"
    default_database: str | None = None
    default_schema: str | None = None
    persist: bool = False


class SqlLineageResult(APIModel):
    statements_parsed: int = 0
    table_edges: list[LineageEdgeCreate] = Field(default_factory=list)
    column_edges: list[LineageEdgeCreate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
