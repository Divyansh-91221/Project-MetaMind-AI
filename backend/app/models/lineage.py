"""Lineage persistence models.

PostgreSQL - not the graph and definitely not the vector store - is the source of truth for
lineage. Neo4j is a rebuildable projection of these rows.

Two tables:

``lineage_edges``
    The current, de-duplicated state of a relationship between two entities.
``lineage_observations``
    Append-only evidence: every time an extractor observes the relationship it records how,
    when, with what confidence and with what supporting evidence. This is what makes lineage
    auditable and lets confidence be recomputed from history instead of overwritten.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import (
    LineageLevel,
    LineageMethod,
    RelationshipType,
    VerificationStatus,
)
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.metadata import MetadataEntity


class LineageEdge(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A directed relationship: ``target`` is derived from / depends on ``source``."""

    __tablename__ = "lineage_edges"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "target_id",
            "relationship",
            "level",
            name="uq_lineage_edges_identity",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint("source_id <> target_id", name="no_self_loop"),
        Index("ix_lineage_edges_source", "source_id"),
        Index("ix_lineage_edges_target", "target_id"),
        Index("ix_lineage_edges_level_method", "level", "method"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("metadata_entities.id", ondelete="CASCADE"), nullable=False
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("metadata_entities.id", ondelete="CASCADE"), nullable=False
    )

    relationship_type: Mapped[RelationshipType] = mapped_column(
        "relationship",
        SAEnum(RelationshipType, name="relationship_type"),
        nullable=False,
        default=RelationshipType.DERIVED_FROM,
    )
    level: Mapped[LineageLevel] = mapped_column(
        SAEnum(LineageLevel, name="lineage_level"), nullable=False, default=LineageLevel.TABLE
    )
    method: Mapped[LineageMethod] = mapped_column(
        SAEnum(LineageMethod, name="lineage_method"),
        nullable=False,
        default=LineageMethod.CONNECTOR_DECLARED,
    )

    transformation: Mapped[str | None] = mapped_column(Text, nullable=True)
    pipeline_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("metadata_entities.id", ondelete="SET NULL"), nullable=True
    )
    job_run_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        SAEnum(VerificationStatus, name="verification_status"),
        nullable=False,
        default=VerificationStatus.UNVERIFIED,
    )
    verified_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observation_count: Mapped[int] = mapped_column(default=1, nullable=False)

    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    properties: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    source: Mapped[MetadataEntity] = relationship(foreign_keys=[source_id], lazy="joined")
    target: Mapped[MetadataEntity] = relationship(foreign_keys=[target_id], lazy="joined")
    pipeline: Mapped[MetadataEntity | None] = relationship(foreign_keys=[pipeline_id])
    observations: Mapped[list[LineageObservation]] = relationship(
        back_populates="edge", cascade="all, delete-orphan"
    )

    @property
    def is_inferred(self) -> bool:
        """AI-inferred edges must always be visually and programmatically distinguishable."""
        return self.method is LineageMethod.AI_INFERRED

    def __repr__(self) -> str:  # pragma: no cover
        return f"<LineageEdge {self.source_id} -[{self.relationship_type}]-> {self.target_id}>"


class LineageObservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Append-only provenance record for a single lineage observation."""

    __tablename__ = "lineage_observations"
    __table_args__ = (
        Index("ix_lineage_observations_edge", "edge_id"),
        Index("ix_lineage_observations_observed_at", "observed_at"),
    )

    edge_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("lineage_edges.id", ondelete="CASCADE"), nullable=False
    )
    method: Mapped[LineageMethod] = mapped_column(
        SAEnum(LineageMethod, name="lineage_method", create_type=False), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    extractor: Mapped[str | None] = mapped_column(String(128), nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    edge: Mapped[LineageEdge] = relationship(back_populates="observations")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<LineageObservation {self.method} conf={self.confidence:.2f}>"
