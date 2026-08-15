"""Freshness tracking and root-cause explanation.

"Why is the revenue dashboard stale?" is a lineage question, not a metrics question: the
answer is almost always an upstream table or a failed pipeline. This service walks upstream
from the asset and reports the first stale ancestors and failed jobs it finds, with evidence.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import EntityType, QualityStatus
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.graph.base import GraphStore
from app.graph.lineage_traversal import get_upstream
from app.graph.neo4j_client import get_graph_store
from app.repositories.metadata_repository import MetadataRepository
from app.repositories.quality_repository import QualityRepository
from app.schemas.quality import FreshnessRead, StalenessExplanation
from app.utils.timestamps import age_hours, utcnow

logger = get_logger(__name__)

DEFAULT_SLA_HOURS = 24.0


class FreshnessService:
    def __init__(self, session: AsyncSession, graph: GraphStore | None = None) -> None:
        self.session = session
        self.graph = graph or get_graph_store()
        self.repo = QualityRepository(session)
        self.metadata_repo = MetadataRepository(session)

    async def get_freshness(self, urn: str) -> FreshnessRead | None:
        entity = await self.metadata_repo.get_by_urn(urn)
        if entity is None:
            raise NotFoundError(f"No catalog entity with URN '{urn}'.")
        record = await self.repo.get_freshness(entity.id)
        if record is None:
            return None
        return self._to_schema(urn, record)

    async def record_refresh(
        self,
        urn: str,
        *,
        last_updated_at: Any = None,
        expected_interval_hours: float | None = None,
        failure_reason: str | None = None,
    ) -> FreshnessRead:
        entity = await self.metadata_repo.get_by_urn(urn)
        if entity is None:
            raise NotFoundError(f"No catalog entity with URN '{urn}'.")

        last_updated = last_updated_at or utcnow()
        sla = expected_interval_hours or DEFAULT_SLA_HOURS
        age = age_hours(last_updated) or 0.0
        status = (
            QualityStatus.FAIL
            if age > sla
            else QualityStatus.WARN
            if age > sla * 0.8
            else QualityStatus.PASS
        )
        record = await self.repo.upsert_freshness(
            entity.id,
            last_updated_at=last_updated,
            expected_interval_hours=sla,
            status=status,
            failure_reason=failure_reason,
        )
        return self._to_schema(urn, record)

    async def explain_staleness(self, urn: str, *, depth: int = 6) -> StalenessExplanation:
        """Trace a stale asset back to its root cause through lineage."""
        entity = await self.metadata_repo.get_by_urn(urn)
        if entity is None:
            raise NotFoundError(f"No catalog entity with URN '{urn}'.")

        record = await self.repo.get_freshness(entity.id)
        age = age_hours(record.last_updated_at) if record else None
        sla = (record.expected_interval_hours if record else None) or DEFAULT_SLA_HOURS
        is_stale = bool(record and record.status is not QualityStatus.PASS) or (
            age is not None and age > sla
        )

        explanation = StalenessExplanation(entity_urn=urn, is_stale=is_stale, age_hours=age)
        if record and record.failure_reason:
            explanation.likely_causes.append(record.failure_reason)

        upstream = await get_upstream(self.graph, urn, depth=depth)
        upstream_nodes = [node for node in upstream.nodes if node.urn != urn]
        if not upstream_nodes:
            if is_stale and not explanation.likely_causes:
                explanation.likely_causes.append(
                    "No upstream lineage is registered for this asset, so the cause cannot be "
                    "traced automatically."
                )
            return explanation

        upstream_entities = await self.metadata_repo.get_many_by_urns(
            [node.urn for node in upstream_nodes]
        )
        by_urn = {item.urn: item for item in upstream_entities}
        freshness_by_id = await self.repo.get_freshness_many(
            [item.id for item in upstream_entities]
        )

        for node in sorted(upstream_nodes, key=lambda n: n.depth):
            item = by_urn.get(node.urn)
            if item is None:
                continue

            if item.entity_type is EntityType.PIPELINE:
                status = str(item.properties.get("last_status", "")).upper()
                if status in {"FAILED", "ERROR", "TIMEOUT"}:
                    explanation.failed_pipelines.append(
                        {
                            "urn": item.urn,
                            "name": item.qualified_name,
                            "status": status,
                            "error": item.properties.get("last_error"),
                            "distance": node.depth,
                        }
                    )
                    explanation.likely_causes.append(
                        f"Pipeline {item.qualified_name} last run status is {status}."
                    )
                continue

            upstream_record = freshness_by_id.get(item.id)
            if upstream_record and upstream_record.status is not QualityStatus.PASS:
                explanation.stale_upstream_assets.append(
                    {
                        "urn": item.urn,
                        "name": item.qualified_name,
                        "status": upstream_record.status.value,
                        "age_hours": age_hours(upstream_record.last_updated_at),
                        "distance": node.depth,
                        "reason": upstream_record.failure_reason,
                    }
                )
                explanation.likely_causes.append(
                    f"Upstream asset {item.qualified_name} is {upstream_record.status.value}."
                )

        if is_stale and not explanation.likely_causes:
            explanation.likely_causes.append(
                "All upstream assets are fresh; investigate the asset's own refresh schedule."
            )
        logger.info(
            "staleness_explained",
            extra={"urn": urn, "causes": len(explanation.likely_causes)},
        )
        return explanation

    @staticmethod
    def _to_schema(urn: str, record: Any) -> FreshnessRead:
        age = age_hours(record.last_updated_at)
        sla = record.expected_interval_hours or DEFAULT_SLA_HOURS
        return FreshnessRead(
            entity_urn=urn,
            last_updated_at=record.last_updated_at,
            last_successful_run_at=record.last_successful_run_at,
            expected_interval_hours=record.expected_interval_hours,
            age_hours=age,
            is_stale=age is None or age > sla,
            status=record.status,
            failure_reason=record.failure_reason,
        )
