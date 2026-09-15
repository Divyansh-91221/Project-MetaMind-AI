"""Metadata Enrichment ("Upload & Enrich") API contracts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.core.constants import (
    EnrichmentIssueSeverity,
    EnrichmentIssueStatus,
    EnrichmentIssueType,
    EnrichmentMappingStatus,
    EnrichmentStage,
)
from app.schemas.common import APIModel


class EnrichmentRunCreate(APIModel):
    """Form fields accompanying the file upload."""

    dataset_name: str
    source_system: str | None = None
    business_domain: str | None = None
    description: str | None = None


class EnrichmentRunRead(APIModel):
    id: uuid.UUID
    dataset_name: str
    source_system: str | None = None
    business_domain: str | None = None
    description: str | None = None
    stage: EnrichmentStage
    uploaded_files: list[dict[str, Any]] = Field(default_factory=list)
    structured_summary: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    mapping_count: int = 0
    issue_count: int = 0
    open_issue_count: int = 0
    created_at: datetime
    completed_at: datetime | None = None


class EnrichmentColumnRead(APIModel):
    id: uuid.UUID
    sheet_name: str | None = None
    dataset_name: str
    column_name: str
    data_type: str | None = None
    nullable: bool | None = None
    sample_values: list[Any] = Field(default_factory=list)
    detected_pii: bool = False
    detected_unit: str | None = None
    entity_urn: str | None = None


class EnrichmentMappingCandidate(APIModel):
    term: str
    confidence: float
    source: str


class EnrichmentMappingRead(APIModel):
    id: uuid.UUID
    dataset_name: str
    column_name: str
    business_term: str | None = None
    business_definition: str | None = None
    document_title: str | None = None
    document_source: str | None = None
    evidence_excerpt: str | None = None
    confidence: float
    method: str
    candidates: list[EnrichmentMappingCandidate] = Field(default_factory=list)
    status: EnrichmentMappingStatus
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    entity_urn: str | None = None


class EnrichmentIssueRead(APIModel):
    id: uuid.UUID
    mapping_id: uuid.UUID | None = None
    dataset_name: str | None = None
    column_name: str | None = None
    issue_type: EnrichmentIssueType
    severity: EnrichmentIssueSeverity
    explanation: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    recommendation: str | None = None
    status: EnrichmentIssueStatus


class EnrichmentReviewRequest(APIModel):
    mapping_id: uuid.UUID
    action: Literal["approve", "reject", "edit"]
    edited_term: str | None = None
    edited_definition: str | None = None


class EnrichmentIntegrationResult(APIModel):
    integrated_count: int
    entity_urns: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
