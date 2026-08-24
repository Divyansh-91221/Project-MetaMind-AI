"""Trust Center API contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.common import APIModel


class TrustDimension(APIModel):
    key: str
    label: str
    score: int = Field(ge=0, le=100)
    status: Literal["HEALTHY", "WARNING", "CRITICAL", "PENDING_REVIEW", "UNKNOWN"]
    reason: str
    evidence: list[str] = Field(default_factory=list)


class ReliabilitySummary(APIModel):
    freshness_status: str
    freshness_last_updated_at: datetime | None = None
    freshness_age_hours: float | None = None
    freshness_expected_interval_hours: float | None = None
    is_stale: bool = False
    freshness_failure_reason: str | None = None
    quality_score: int = Field(ge=0, le=100)
    quality_warning_count: int = 0
    completeness: float | None = None
    validity: float | None = None
    null_rate: float | None = None
    anomaly_count: int | None = None


class DependencyRiskSummary(APIModel):
    upstream_asset_count: int = 0
    downstream_asset_count: int = 0
    critical_downstream_consumers: int = 0
    dashboards_affected: int = 0
    reports_affected: int = 0
    dependency_risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    reason: str
    unverified_dependency_count: int = 0
    inferred_path_count: int = 0


class SensitiveFieldDetection(APIModel):
    assignment_id: str
    entity_urn: str
    qualified_name: str
    column_name: str | None = None
    classification: str
    confidence: float | None = None
    detection_source: str | None = None
    review_status: Literal["CONFIRMED", "PENDING_REVIEW"]
    evidence: dict[str, Any] = Field(default_factory=dict)


class OwnershipSummary(APIModel):
    owner: str | None = None
    steward: str | None = None
    status: Literal["ASSIGNED", "UNOWNED"]
    team: str | None = None
    warning: str | None = None


class TrustIssue(APIModel):
    code: str
    severity: Literal["WARNING", "CRITICAL"]
    title: str
    detail: str
    target_page: Literal["quality", "impact", "governance", "lineage", "asset"]
    target_url: str


class TrustScoreExplanation(APIModel):
    positives: list[str] = Field(default_factory=list)
    negatives: list[str] = Field(default_factory=list)


class AssetTrustSummary(APIModel):
    entity_urn: str
    asset_name: str
    platform: str
    asset_type: str
    description: str | None = None
    owner: str | None = None
    last_updated_at: datetime | None = None
    trust_score: int = Field(ge=0, le=100)
    trust_status: str
    dimensions: list[TrustDimension] = Field(default_factory=list)
    reliability: ReliabilitySummary
    dependency_risk: DependencyRiskSummary
    sensitive_data: list[SensitiveFieldDetection] = Field(default_factory=list)
    ownership: OwnershipSummary
    issues: list[TrustIssue] = Field(default_factory=list)
    explanation: TrustScoreExplanation
