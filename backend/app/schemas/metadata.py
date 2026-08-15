"""Metadata catalog API contracts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from app.core.constants import EntityType
from app.schemas.common import APIModel


class MetadataEntityBase(APIModel):
    entity_type: EntityType
    platform: str = "unknown"
    name: str
    qualified_name: str
    display_name: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)


class MetadataEntityCreate(MetadataEntityBase):
    """Payload used by connectors and manual curation."""

    parent_urn: str | None = None
    data_type: str | None = None
    ordinal_position: int | None = None
    is_nullable: bool | None = None
    is_primary_key: bool | None = None
    row_count: int | None = None
    source_system: str | None = None


class MetadataEntityUpdate(APIModel):
    """Partial update; only curated fields are user-editable."""

    display_name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    properties: dict[str, Any] | None = None
    is_deprecated: bool | None = None


class MetadataEntityRead(MetadataEntityBase):
    id: uuid.UUID
    urn: str
    parent_id: uuid.UUID | None = None
    data_source_id: uuid.UUID | None = None
    data_type: str | None = None
    ordinal_position: int | None = None
    is_nullable: bool | None = None
    is_primary_key: bool | None = None
    row_count: int | None = None
    source_system: str | None = None
    is_deprecated: bool = False
    last_seen_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ColumnSummary(APIModel):
    """Compact column projection used on the asset details page."""

    urn: str
    name: str
    data_type: str | None = None
    ordinal_position: int | None = None
    is_nullable: bool | None = None
    is_primary_key: bool | None = None
    description: str | None = None
    classifications: list[str] = Field(default_factory=list)


class MetadataEntityDetail(MetadataEntityRead):
    """Full asset view: technical metadata plus business and governance context."""

    parent_urn: str | None = None
    columns: list[ColumnSummary] = Field(default_factory=list)
    owners: list[dict[str, Any]] = Field(default_factory=list)
    classifications: list[dict[str, Any]] = Field(default_factory=list)
    business_terms: list[dict[str, Any]] = Field(default_factory=list)
    quality: dict[str, Any] = Field(default_factory=dict)
    upstream_count: int = 0
    downstream_count: int = 0


class MetadataFilter(APIModel):
    """Query filters for the catalog listing endpoint."""

    entity_type: EntityType | None = None
    platform: str | None = None
    parent_urn: str | None = None
    search: str | None = Field(default=None, max_length=256)
    tag: str | None = None
    include_deleted: bool = False


class IngestionRequest(APIModel):
    """Trigger a metadata ingestion run for a registered connector."""

    connector: str = Field(description="Registered connector name, e.g. 'demo' or 'postgres'.")
    data_source_name: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    full_refresh: bool = False
    extract_lineage: bool = True

    @field_validator("connector")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.strip().lower()


class IngestionResult(APIModel):
    """Outcome of an ingestion run - also written to the audit trail."""

    run_id: uuid.UUID
    connector: str
    data_source: str
    entities_created: int = 0
    entities_updated: int = 0
    lineage_edges_created: int = 0
    lineage_edges_updated: int = 0
    documents_indexed: int = 0
    errors: list[str] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime
    duration_seconds: float = 0.0
