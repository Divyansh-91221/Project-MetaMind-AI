"""Metadata Enrichment models: "Upload & Enrich" runs, discovered columns, AI mappings and
quality issues.

Additive-only, isolated tables. Nothing here modifies ``metadata_entities`` or any other
existing table: an enrichment run stays a sandboxed draft until it is explicitly integrated,
at which point :mod:`app.services.enrichment.integration` writes ordinary
:class:`app.models.metadata.MetadataEntity` rows through the same code path regular ingestion
uses. This file only stores the draft/review state, never a parallel catalog.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import (
    EnrichmentIssueSeverity,
    EnrichmentIssueStatus,
    EnrichmentIssueType,
    EnrichmentMappingStatus,
    EnrichmentStage,
)
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EnrichmentRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One "Upload & Enrich" job: from raw upload through to catalog integration."""

    __tablename__ = "enrichment_runs"
    __table_args__ = (Index("ix_enrichment_runs_stage", "stage"),)

    dataset_name: Mapped[str] = mapped_column(String(512), nullable=False)
    source_system: Mapped[str | None] = mapped_column(String(255), nullable=True)
    business_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    stage: Mapped[EnrichmentStage] = mapped_column(
        SAEnum(EnrichmentStage, name="enrichment_stage"),
        nullable=False,
        default=EnrichmentStage.UPLOADED,
    )
    uploaded_files: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    structured_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    mapping_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    columns: Mapped[list[EnrichmentColumn]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    mappings: Mapped[list[EnrichmentMapping]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    issues: Mapped[list[EnrichmentIssue]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class EnrichmentColumn(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A technical column discovered from an uploaded CSV/XLSX, before any mapping."""

    __tablename__ = "enrichment_columns"
    __table_args__ = (Index("ix_enrichment_columns_run", "run_id"),)

    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("enrichment_runs.id", ondelete="CASCADE"), nullable=False
    )
    sheet_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dataset_name: Mapped[str] = mapped_column(String(512), nullable=False)
    column_name: Mapped[str] = mapped_column(String(255), nullable=False)
    data_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    nullable: Mapped[bool | None] = mapped_column(nullable=True)
    sample_values: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    detected_pii: Mapped[bool] = mapped_column(nullable=False, default=False)
    detected_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    entity_urn: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    run: Mapped[EnrichmentRun] = relationship(back_populates="columns")


class EnrichmentMapping(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """AI-generated (or human-edited) business/documentation mapping for one column."""

    __tablename__ = "enrichment_mappings"
    __table_args__ = (Index("ix_enrichment_mappings_run", "run_id"),)

    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("enrichment_runs.id", ondelete="CASCADE"), nullable=False
    )
    dataset_name: Mapped[str] = mapped_column(String(512), nullable=False)
    column_name: Mapped[str] = mapped_column(String(255), nullable=False)

    business_term: Mapped[str | None] = mapped_column(String(255), nullable=True)
    business_definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    document_source: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    evidence_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)

    confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    method: Mapped[str] = mapped_column(String(64), nullable=False, default="NONE")
    candidates: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    status: Mapped[EnrichmentMappingStatus] = mapped_column(
        SAEnum(EnrichmentMappingStatus, name="enrichment_mapping_status"),
        nullable=False,
        default=EnrichmentMappingStatus.PENDING_REVIEW,
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entity_urn: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    run: Mapped[EnrichmentRun] = relationship(back_populates="mappings")
    issues: Mapped[list[EnrichmentIssue]] = relationship(back_populates="mapping")


class EnrichmentIssue(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A dynamically-detected quality/validation finding for a run, optionally tied to a mapping."""

    __tablename__ = "enrichment_issues"
    __table_args__ = (Index("ix_enrichment_issues_run", "run_id"),)

    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("enrichment_runs.id", ondelete="CASCADE"), nullable=False
    )
    mapping_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("enrichment_mappings.id", ondelete="SET NULL"), nullable=True
    )
    dataset_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    column_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    issue_type: Mapped[EnrichmentIssueType] = mapped_column(
        SAEnum(EnrichmentIssueType, name="enrichment_issue_type"), nullable=False
    )
    severity: Mapped[EnrichmentIssueSeverity] = mapped_column(
        SAEnum(EnrichmentIssueSeverity, name="enrichment_issue_severity"),
        nullable=False,
        default=EnrichmentIssueSeverity.MEDIUM,
    )
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[EnrichmentIssueStatus] = mapped_column(
        SAEnum(EnrichmentIssueStatus, name="enrichment_issue_status"),
        nullable=False,
        default=EnrichmentIssueStatus.OPEN,
    )

    run: Mapped[EnrichmentRun] = relationship(back_populates="issues")
    mapping: Mapped[EnrichmentMapping | None] = relationship(back_populates="issues")
