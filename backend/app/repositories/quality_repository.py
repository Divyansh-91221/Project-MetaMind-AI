"""Data access for quality metrics and freshness records."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import QualityDimension, QualityStatus
from app.models.quality import FreshnessRecord, QualityMetric
from app.utils.timestamps import utcnow


class QualityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_metric(
        self,
        entity_id: uuid.UUID,
        *,
        dimension: QualityDimension,
        metric_name: str,
        value: float | None = None,
        unit: str | None = None,
        threshold: float | None = None,
        status: QualityStatus = QualityStatus.UNKNOWN,
        measured_at: Any = None,
        source: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> QualityMetric:
        metric = QualityMetric(
            entity_id=entity_id,
            dimension=dimension,
            metric_name=metric_name,
            value=value,
            unit=unit,
            threshold=threshold,
            status=status,
            measured_at=measured_at or utcnow(),
            source=source,
            details=details or {},
        )
        self.session.add(metric)
        await self.session.flush()
        return metric

    async def latest_metrics(
        self, entity_id: uuid.UUID, *, limit: int = 50
    ) -> list[QualityMetric]:
        stmt = (
            select(QualityMetric)
            .where(QualityMetric.entity_id == entity_id)
            .order_by(QualityMetric.measured_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_freshness(self, entity_id: uuid.UUID) -> FreshnessRecord | None:
        stmt = select(FreshnessRecord).where(FreshnessRecord.entity_id == entity_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_freshness_many(
        self, entity_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, FreshnessRecord]:
        if not entity_ids:
            return {}
        stmt = select(FreshnessRecord).where(FreshnessRecord.entity_id.in_(entity_ids))
        return {r.entity_id: r for r in (await self.session.execute(stmt)).scalars().all()}

    async def upsert_freshness(self, entity_id: uuid.UUID, **values: Any) -> FreshnessRecord:
        record = await self.get_freshness(entity_id)
        if record is None:
            record = FreshnessRecord(entity_id=entity_id, **values)
            self.session.add(record)
        else:
            for key, value in values.items():
                if value is not None:
                    setattr(record, key, value)
        await self.session.flush()
        return record

    async def stale_entities(self, *, limit: int = 50) -> list[FreshnessRecord]:
        stmt = (
            select(FreshnessRecord)
            .where(FreshnessRecord.status.in_([QualityStatus.FAIL, QualityStatus.WARN]))
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())
