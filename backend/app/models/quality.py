"""Data quality and freshness models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import QualityDimension, QualityStatus
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.metadata import MetadataEntity


class QualityMetric(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single quality measurement for an asset at a point in time.

    Kept append-only so trends and regressions can be analysed, and so the Copilot can
    answer "why is the revenue dashboard stale?" with a timestamped fact.
    """

    __tablename__ = "quality_metrics"
    __table_args__ = (
        Index("ix_quality_metrics_entity_dimension", "entity_id", "dimension"),
        Index("ix_quality_metrics_measured_at", "measured_at"),
    )

    entity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("metadata_entities.id", ondelete="CASCADE"), nullable=False
    )
    dimension: Mapped[QualityDimension] = mapped_column(
        SAEnum(QualityDimension, name="quality_dimension"), nullable=False
    )
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[QualityStatus] = mapped_column(
        SAEnum(QualityStatus, name="quality_status"), nullable=False, default=QualityStatus.UNKNOWN
    )
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    entity: Mapped[MetadataEntity] = relationship(back_populates="quality_metrics")


class FreshnessRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Latest refresh state of an asset plus its freshness SLA."""

    __tablename__ = "freshness_records"
    __table_args__ = (Index("ix_freshness_records_entity", "entity_id", unique=True),)

    entity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("metadata_entities.id", ondelete="CASCADE"), nullable=False
    )
    last_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expected_interval_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[QualityStatus] = mapped_column(
        SAEnum(QualityStatus, name="quality_status", create_type=False),
        nullable=False,
        default=QualityStatus.UNKNOWN,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    entity: Mapped[MetadataEntity] = relationship()
