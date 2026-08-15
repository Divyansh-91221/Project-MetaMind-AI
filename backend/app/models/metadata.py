"""Catalog persistence models.

Design note
-----------
Rather than one table per asset type, the catalog uses a single ``metadata_entities`` table
keyed by a stable URN with an ``entity_type`` discriminator, a self-referencing ``parent_id``
hierarchy and a JSONB ``properties`` bag for type-specific technical metadata. Frequently
filtered technical attributes are promoted to real columns.

This keeps new asset types (a new BI tool, a new streaming platform) purely additive - no
schema migration is needed to catalog them - while still giving typed access through the
Pydantic schemas in :mod:`app.schemas.metadata`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import EntityType, PlatformType
from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.governance import EntityClassification, EntityOwner
    from app.models.quality import QualityMetric


class DataSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A registered enterprise system the platform ingests metadata from.

    ``config`` never holds secrets. Credentials are resolved at runtime from the
    environment or a secret manager using ``secret_ref``.
    """

    __tablename__ = "data_sources"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    connector_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    platform: Mapped[PlatformType] = mapped_column(
        SAEnum(PlatformType, name="platform_type"),
        nullable=False,
        default=PlatformType.UNKNOWN,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    secret_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ingestion_status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    entities: Mapped[list[MetadataEntity]] = relationship(
        back_populates="data_source", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DataSource {self.name} ({self.connector_type})>"


class MetadataEntity(TimestampMixin, SoftDeleteMixin, Base):
    """Any catalog object: database, schema, table, column, pipeline, dataset, dashboard, KPI."""

    __tablename__ = "metadata_entities"
    __table_args__ = (
        UniqueConstraint("urn", name="uq_metadata_entities_urn"),
        Index("ix_metadata_entities_type_platform", "entity_type", "platform"),
        Index("ix_metadata_entities_qualified_name", "qualified_name"),
        Index("ix_metadata_entities_parent", "parent_id"),
        Index("ix_metadata_entities_name_lower", "name"),
    )

    # Deterministic UUIDv5 of the URN - see app.utils.identifiers.urn_to_uuid.
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    urn: Mapped[str] = mapped_column(String(1024), nullable=False)

    entity_type: Mapped[EntityType] = mapped_column(
        SAEnum(EntityType, name="entity_type"), nullable=False, index=True
    )
    platform: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")

    name: Mapped[str] = mapped_column(String(512), nullable=False)
    qualified_name: Mapped[str] = mapped_column(String(1024), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("metadata_entities.id", ondelete="CASCADE"), nullable=True
    )
    data_source_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True
    )

    # --- Promoted technical metadata (nullable; meaningful per entity type) ---
    data_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ordinal_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_nullable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_primary_key: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- Extensible payloads ------------------------------------------------
    properties: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    source_system: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_deprecated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Relationships ------------------------------------------------------
    parent: Mapped[MetadataEntity | None] = relationship(
        remote_side="MetadataEntity.id", back_populates="children"
    )
    children: Mapped[list[MetadataEntity]] = relationship(
        back_populates="parent", cascade="all, delete-orphan", passive_deletes=True
    )
    data_source: Mapped[DataSource | None] = relationship(back_populates="entities")
    owners: Mapped[list[EntityOwner]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )
    classifications: Mapped[list[EntityClassification]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )
    quality_metrics: Mapped[list[QualityMetric]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MetadataEntity {self.entity_type}:{self.qualified_name}>"
