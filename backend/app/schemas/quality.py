"""Data quality and freshness API contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.core.constants import QualityDimension, QualityStatus
from app.schemas.common import APIModel


class QualityMetricRead(APIModel):
    dimension: QualityDimension
    metric_name: str
    value: float | None = None
    unit: str | None = None
    threshold: float | None = None
    status: QualityStatus = QualityStatus.UNKNOWN
    measured_at: datetime
    source: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class QualityMetricCreate(APIModel):
    entity_urn: str
    dimension: QualityDimension
    metric_name: str
    value: float | None = None
    unit: str | None = None
    threshold: float | None = None
    status: QualityStatus = QualityStatus.UNKNOWN
    measured_at: datetime | None = None
    source: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class FreshnessRead(APIModel):
    entity_urn: str
    last_updated_at: datetime | None = None
    last_successful_run_at: datetime | None = None
    expected_interval_hours: float | None = None
    age_hours: float | None = None
    is_stale: bool = False
    status: QualityStatus = QualityStatus.UNKNOWN
    failure_reason: str | None = None


class QualityProfile(APIModel):
    """Aggregated quality view for an asset, used by the UI and the Copilot."""

    entity_urn: str
    entity_name: str
    overall_status: QualityStatus = QualityStatus.UNKNOWN
    freshness: FreshnessRead | None = None
    metrics: list[QualityMetricRead] = Field(default_factory=list)
    failing_dimensions: list[QualityDimension] = Field(default_factory=list)


class StalenessExplanation(APIModel):
    """Root-cause style answer for "why is this dashboard stale?".

    The upstream chain is resolved from lineage, so the explanation is evidence-backed.
    """

    entity_urn: str
    is_stale: bool = False
    age_hours: float | None = None
    likely_causes: list[str] = Field(default_factory=list)
    stale_upstream_assets: list[dict[str, Any]] = Field(default_factory=list)
    failed_pipelines: list[dict[str, Any]] = Field(default_factory=list)
