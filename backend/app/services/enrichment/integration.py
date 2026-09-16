"""Push INTEGRATION_READY Metadata Enrichment mappings into the existing MetaMind catalog.

This is the seam between the enrichment draft state and the real platform: everything here
goes through the exact same services regular connector ingestion uses
(:class:`MetadataService.upsert_raw_entity`, :class:`GlossaryService`,
:class:`ClassificationService`) so integrated assets are indistinguishable from any other
catalog entity to the Catalog, Lineage, Governance, Trust Center and Copilot.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import RawEntity
from app.core.constants import (
    AuditAction,
    EnrichmentMappingStatus,
    EnrichmentStage,
    EntityType,
    PlatformType,
)
from app.repositories.audit_repository import AuditRepository
from app.repositories.enrichment_repository import EnrichmentRepository
from app.schemas.enrichment import EnrichmentIntegrationResult
from app.schemas.glossary import BusinessTermCreate, TermAssignmentRequest
from app.services.enrichment.enrichment_service import EnrichmentService
from app.services.glossary.glossary_service import GlossaryService
from app.services.governance.classification_service import ClassificationService
from app.services.metadata.metadata_service import MetadataService
from app.services.search.hybrid_search import SearchService
from app.utils.identifiers import normalize_name


class EnrichmentIntegrationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = EnrichmentRepository(session)
        self.enrichment = EnrichmentService(session)
        self.metadata = MetadataService(session)
        self.glossary = GlossaryService(session)
        self.classification = ClassificationService(session)
        self.search = SearchService(session)
        self.audit = AuditRepository(session)

    async def integrate(self, run_id: uuid.UUID, *, principal: str) -> EnrichmentIntegrationResult:
        run = await self.enrichment.assert_ready_for_integration(run_id)

        mappings = await self.repo.list_mappings(run.id)
        columns = {(c.dataset_name, c.column_name): c for c in await self.repo.list_columns(run.id)}
        platform = normalize_name(run.source_system or "enrichment")

        data_source = await self.metadata.repo.upsert_data_source(
            run.source_system or f"enrichment-upload-{run.id}",
            connector_type="enrichment",
            platform=PlatformType.UNKNOWN,
            description=run.description or f"Uploaded via Metadata Enrichment ({run.dataset_name}).",
            config={},
            enabled=True,
        )

        integrated_urns: list[str] = []
        skipped: list[str] = []
        table_entities: dict[str, Any] = {}

        for mapping in mappings:
            if mapping.status is EnrichmentMappingStatus.REJECTED:
                skipped.append(f"{mapping.dataset_name}.{mapping.column_name} (rejected)")
                continue

            if mapping.dataset_name not in table_entities:
                table_raw = RawEntity(
                    entity_type=EntityType.TABLE,
                    name=mapping.dataset_name,
                    qualified_name=mapping.dataset_name,
                    platform=platform,
                    description=run.description,
                    tags=["enrichment-upload"],
                    properties={"enrichment_run_id": str(run.id)},
                )
                table_entity, _ = await self.metadata.upsert_raw_entity(
                    table_raw, data_source_id=data_source.id
                )
                table_entities[mapping.dataset_name] = table_entity
                integrated_urns.append(table_entity.urn)

            table_entity = table_entities[mapping.dataset_name]
            column = columns.get((mapping.dataset_name, mapping.column_name))

            column_raw = RawEntity(
                entity_type=EntityType.COLUMN,
                name=mapping.column_name,
                qualified_name=f"{mapping.dataset_name}.{mapping.column_name}",
                platform=platform,
                parent_qualified_name=mapping.dataset_name,
                parent_entity_type=EntityType.TABLE,
                description=mapping.business_definition,
                data_type=column.data_type if column else None,
                is_nullable=column.nullable if column else None,
                properties={
                    "enrichment": {
                        "run_id": str(run.id),
                        "confidence": mapping.confidence,
                        "method": mapping.method,
                        "document_title": mapping.document_title,
                        "document_source": mapping.document_source,
                        "evidence_excerpt": mapping.evidence_excerpt,
                        "review_status": mapping.status.value,
                        "reviewed_by": mapping.reviewed_by,
                    }
                },
            )
            column_entity, _ = await self.metadata.upsert_raw_entity(
                column_raw, data_source_id=data_source.id, parent_id=table_entity.id
            )
            integrated_urns.append(column_entity.urn)

            mapping.entity_urn = column_entity.urn
            if column is not None:
                column.entity_urn = column_entity.urn

            if mapping.business_term:
                # A human-edited mapping may name a term that doesn't exist in the glossary yet -
                # create it on the spot rather than letting one unresolved name abort the whole
                # batch's integration.
                existing_term = await self.glossary.repo.get_by_name(mapping.business_term)
                if existing_term is None:
                    await self.glossary.create_term(
                        BusinessTermCreate(
                            name=mapping.business_term,
                            domain=run.business_domain or "enterprise",
                            definition=mapping.business_definition
                            or f"Business term captured via Metadata Enrichment for '{run.dataset_name}'.",
                        )
                    )
                await self.glossary.assign_term(
                    TermAssignmentRequest(
                        term_name=mapping.business_term,
                        entity_urn=column_entity.urn,
                        method="HUMAN_APPROVED" if mapping.reviewed_by else "AI_MAPPED",
                        confidence=mapping.confidence,
                    )
                )

            # Reuse the same rule-based classifier every other ingestion path uses, rather than
            # trusting the enrichment heuristic alone - the column now exists as a real entity.
            await self.classification.apply(column_entity, principal=principal)

        await self.repo.set_stage(run, EnrichmentStage.INTEGRATED)
        await self.session.flush()

        if integrated_urns:
            await self.search.pipeline.index_catalog(entity_urns=integrated_urns, force=True)

        await self.audit.record(
            AuditAction.ENRICHMENT_INTEGRATED,
            principal=principal,
            resource_type="enrichment_run",
            summary=f"Integrated {len(integrated_urns)} asset(s) from '{run.dataset_name}' into the catalog.",
            payload={"run_id": str(run.id), "entity_urns": integrated_urns},
        )

        return EnrichmentIntegrationResult(
            integrated_count=len(integrated_urns), entity_urns=integrated_urns, skipped=skipped
        )
