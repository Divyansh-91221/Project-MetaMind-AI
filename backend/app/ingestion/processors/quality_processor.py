"""Quality metric ingestion processor."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import MetadataConnector
from app.core.logging import get_logger
from app.schemas.quality import QualityMetricCreate
from app.services.quality.quality_service import QualityService

logger = get_logger(__name__)


@dataclass(slots=True)
class QualityProcessingResult:
    recorded: int = 0
    errors: list[str] = field(default_factory=list)


class QualityProcessor:
    def __init__(self, session: AsyncSession) -> None:
        self.quality = QualityService(session)

    async def process(self, connector: MetadataConnector) -> QualityProcessingResult:
        result = QualityProcessingResult()
        async for metric in connector.extract_quality():
            try:
                await self.quality.record_metric(
                    QualityMetricCreate(
                        entity_urn=metric.entity_urn,
                        dimension=metric.dimension,
                        metric_name=metric.metric_name,
                        value=metric.value,
                        unit=metric.unit,
                        threshold=metric.threshold,
                        status=metric.status,
                        measured_at=metric.measured_at,
                        source=connector.name,
                        details=metric.details,
                    )
                )
                result.recorded += 1
            except Exception as exc:  # noqa: BLE001 - metrics must not fail the whole run
                message = f"{metric.entity_urn} / {metric.metric_name}: {exc}"
                result.errors.append(message)
                logger.warning("quality_metric_failed", extra={"error": message})
        return result
