"""Metadata ingestion pipeline.

Orchestrates one ingestion run end to end::

    connector -> entities -> lineage -> quality -> graph projection -> semantic index -> audit

Every step is isolated: a failure in lineage extraction still leaves the catalog updated, and
the audit trail records exactly what happened.
"""

from __future__ import annotations

import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import MetadataConnector, RawEntity
from app.connectors.registry import create_connector
from app.core.constants import AuditAction, PlatformType
from app.core.exceptions import ConnectorError
from app.core.logging import get_logger
from app.ingestion.processors.lineage_processor import LineageProcessor
from app.ingestion.processors.metadata_processor import MetadataProcessor
from app.ingestion.processors.quality_processor import QualityProcessor
from app.repositories.audit_repository import AuditRepository
from app.repositories.metadata_repository import MetadataRepository
from app.schemas.metadata import IngestionRequest, IngestionResult
from app.services.governance.governance_service import GovernanceService
from app.services.search.hybrid_search import SearchService
from app.utils.timestamps import utcnow

logger = get_logger(__name__)


class IngestionPipeline:
    """Runs a single ingestion job for one connector."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.metadata_repo = MetadataRepository(session)
        self.audit_repo = AuditRepository(session)
        self.metadata_processor = MetadataProcessor(session)
        self.lineage_processor = LineageProcessor(session)
        self.quality_processor = QualityProcessor(session)
        self.governance = GovernanceService(session)
        self.search = SearchService(session)

    async def run(
        self, request: IngestionRequest, *, principal: str = "system"
    ) -> IngestionResult:
        run_id = uuid.uuid4()
        started_at = utcnow()
        started_perf = time.perf_counter()
        errors: list[str] = []

        await self.audit_repo.record(
            AuditAction.INGESTION_STARTED,
            principal=principal,
            resource_type="ingestion",
            summary=f"Ingestion started for connector '{request.connector}'.",
            payload={"run_id": str(run_id), "connector": request.connector},
        )

        connector = create_connector(request.connector, request.config)
        data_source_name = request.data_source_name or f"{request.connector}-default"

        try:
            data_source = await self._register_data_source(connector, data_source_name, request)
            await self.governance.bootstrap()

            entities: list[RawEntity] = [item async for item in connector.extract_entities()]
            metadata_result = await self.metadata_processor.process(
                entities, data_source_id=data_source.id, principal=principal
            )
            errors.extend(metadata_result.errors)

            lineage_created = lineage_updated = 0
            if request.extract_lineage:
                lineage_result = await self.lineage_processor.process(
                    connector, principal=principal
                )
                lineage_created = lineage_result.created
                lineage_updated = lineage_result.updated
                errors.extend(lineage_result.warnings)

            quality_result = await self.quality_processor.process(connector)
            errors.extend(quality_result.errors)

            index_report = await self._reindex(list(metadata_result.urn_to_id))

            data_source.last_ingested_at = utcnow()
            data_source.last_ingestion_status = "SUCCESS" if not errors else "PARTIAL"

            completed_at = utcnow()
            result = IngestionResult(
                run_id=run_id,
                connector=connector.name,
                data_source=data_source_name,
                entities_created=metadata_result.created,
                entities_updated=metadata_result.updated,
                lineage_edges_created=lineage_created,
                lineage_edges_updated=lineage_updated,
                documents_indexed=index_report,
                errors=errors[:50],
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=round(time.perf_counter() - started_perf, 3),
            )

            await self.audit_repo.record(
                AuditAction.INGESTION_COMPLETED,
                principal=principal,
                resource_type="ingestion",
                summary=(
                    f"Ingested {result.entities_created + result.entities_updated} entities and "
                    f"{result.lineage_edges_created + result.lineage_edges_updated} lineage edges."
                ),
                payload=result.model_dump(mode="json"),
            )
            logger.info("ingestion_completed", extra=result.model_dump(mode="json"))
            return result

        except Exception as exc:
            await self.audit_repo.record(
                AuditAction.INGESTION_FAILED,
                principal=principal,
                resource_type="ingestion",
                summary=f"Ingestion failed for connector '{request.connector}'.",
                payload={"run_id": str(run_id), "error": str(exc)},
            )
            logger.exception("ingestion_failed", extra={"connector": request.connector})
            if isinstance(exc, ConnectorError):
                raise
            raise ConnectorError(f"Ingestion failed: {exc}") from exc
        finally:
            await connector.close()

    async def _register_data_source(
        self, connector: MetadataConnector, name: str, request: IngestionRequest
    ):  # type: ignore[no-untyped-def]
        """Create or refresh the data source row backing this connector run."""
        platform = (
            connector.platform
            if connector.platform is not PlatformType.UNKNOWN
            else PlatformType.UNKNOWN
        )
        return await self.metadata_repo.upsert_data_source(
            name,
            connector_type=connector.name,
            platform=platform,
            description=connector.description,
            # Configuration is stored without secrets; credentials stay in the secret store.
            config={k: v for k, v in request.config.items() if "password" not in k.lower()},
            enabled=True,
        )

    async def _reindex(self, urns: list[str]) -> int:
        """Refresh the semantic index for the ingested assets."""
        try:
            report = await self.search.pipeline.index_catalog(entity_urns=urns or None)
            return report.documents_indexed
        except Exception as exc:  # noqa: BLE001 - indexing must not fail ingestion
            logger.warning("reindex_failed", extra={"error": str(exc)})
            return 0
