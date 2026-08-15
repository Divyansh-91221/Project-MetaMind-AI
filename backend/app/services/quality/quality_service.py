"""Data quality service."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import QualityDimension, QualityStatus
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.repositories.metadata_repository import MetadataRepository
from app.repositories.quality_repository import QualityRepository
from app.schemas.quality import (
    QualityMetricCreate,
    QualityMetricRead,
    QualityProfile,
    StalenessExplanation,
)
from app.services.quality.freshness_service import FreshnessService

logger = get_logger(__name__)

_STATUS_SEVERITY = {
    QualityStatus.PASS: 0,
    QualityStatus.UNKNOWN: 1,
    QualityStatus.WARN: 2,
    QualityStatus.FAIL: 3,
}


class QualityService:
    """Records measurements and assembles the quality profile of an asset."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = QualityRepository(session)
        self.metadata_repo = MetadataRepository(session)
        self.freshness = FreshnessService(session)

    async def record_metric(self, payload: QualityMetricCreate) -> QualityMetricRead:
        entity = await self.metadata_repo.get_by_urn(payload.entity_urn)
        if entity is None:
            raise NotFoundError(f"No catalog entity with URN '{payload.entity_urn}'.")

        metric = await self.repo.add_metric(
            entity.id,
            dimension=payload.dimension,
            metric_name=payload.metric_name,
            value=payload.value,
            unit=payload.unit,
            threshold=payload.threshold,
            status=payload.status,
            measured_at=payload.measured_at,
            source=payload.source,
            details=payload.details,
        )

        # Freshness metrics also update the denormalised freshness record used by lineage
        # root-cause analysis.
        if payload.dimension is QualityDimension.FRESHNESS:
            await self.repo.upsert_freshness(
                entity.id,
                last_updated_at=metric.measured_at,
                expected_interval_hours=payload.details.get("expected_interval_hours")
                or payload.threshold,
                status=payload.status,
                failure_reason=payload.details.get("reason"),
            )
        return QualityMetricRead.model_validate(metric)

    async def get_profile(self, urn: str) -> QualityProfile:
        entity = await self.metadata_repo.get_by_urn(urn)
        if entity is None:
            raise NotFoundError(f"No catalog entity with URN '{urn}'.")

        metrics = await self.repo.latest_metrics(entity.id)
        freshness = await self.freshness.get_freshness(urn)

        statuses = [metric.status for metric in metrics]
        if freshness is not None:
            statuses.append(freshness.status)
        overall = max(statuses, key=lambda s: _STATUS_SEVERITY[s], default=QualityStatus.UNKNOWN)

        return QualityProfile(
            entity_urn=urn,
            entity_name=entity.qualified_name,
            overall_status=overall,
            freshness=freshness,
            metrics=[QualityMetricRead.model_validate(metric) for metric in metrics],
            failing_dimensions=sorted(
                {metric.dimension for metric in metrics if metric.status is QualityStatus.FAIL},
                key=lambda dimension: dimension.value,
            ),
        )

    async def explain_staleness(self, urn: str) -> StalenessExplanation:
        return await self.freshness.explain_staleness(urn)

    async def stale_assets(self, *, limit: int = 50) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        for record in await self.repo.stale_entities(limit=limit):
            entity = await self.metadata_repo.get_by_id(record.entity_id)
            if entity is None:
                continue
            results.append(
                {
                    "urn": entity.urn,
                    "qualified_name": entity.qualified_name,
                    "status": record.status.value,
                    "last_updated_at": record.last_updated_at,
                    "failure_reason": record.failure_reason,
                }
            )
        return results
