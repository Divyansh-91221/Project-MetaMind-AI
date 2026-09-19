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

from app.connectors.base import RawEntity, RawLineage
from app.core.constants import (
    AuditAction,
    EnrichmentMappingStatus,
    EnrichmentStage,
    EntityType,
    LineageLevel,
    LineageMethod,
    PlatformType,
    RelationshipType,
)
from app.repositories.audit_repository import AuditRepository
from app.repositories.enrichment_repository import EnrichmentRepository
from app.schemas.enrichment import EnrichmentIntegrationResult
from app.schemas.glossary import BusinessTermCreate, TermAssignmentRequest
from app.services.enrichment.enrichment_service import EnrichmentService
from app.services.glossary.glossary_service import GlossaryService
from app.services.governance.classification_service import ClassificationService
from app.services.lineage.lineage_service import LineageService
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
        dataset_row_counts = {
            item.get("name"): item.get("row_count")
            for item in run.structured_summary.get("datasets", [])
            if item.get("name") and isinstance(item.get("row_count"), int)
        }

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
        integrated_columns: dict[uuid.UUID, Any] = {}

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
                    row_count=dataset_row_counts.get(mapping.dataset_name),
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
            integrated_columns[mapping.id] = column_entity

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

        # Reuse approved glossary links as lineage evidence: an uploaded customer or revenue
        # field can then be traced back to the existing enterprise assets that define it.
        lineage_edges: list[RawLineage] = []
        integrated_ids = {entity.id for entity in table_entities.values()} | {
            entity.id for entity in integrated_columns.values()
        }
        for mapping in mappings:
            target_column = integrated_columns.get(mapping.id)
            if (
                target_column is None
                or mapping.status is EnrichmentMappingStatus.REJECTED
                or not mapping.business_term
            ):
                continue
            term = await self.glossary.repo.get_by_name(mapping.business_term)
            if term is None:
                continue
            for assignment in await self.glossary.repo.assignments_for_term(term.id):
                source = assignment.entity
                if source.id in integrated_ids:
                    continue
                lineage_edges.append(
                    RawLineage(
                        source_urn=source.urn,
                        target_urn=target_column.urn,
                        relationship=RelationshipType.DERIVED_FROM,
                        level=LineageLevel.COLUMN,
                        method=LineageMethod.AI_INFERRED,
                        confidence=mapping.confidence,
                        evidence={
                            "source": "enrichment_business_mapping",
                            "run_id": str(run.id),
                            "business_term": mapping.business_term,
                            "evidence_excerpt": mapping.evidence_excerpt,
                        },
                    )
                )

        # Add a table-level view of the same relationships for users who start exploration from
        # the uploaded dataset rather than one of its columns.
        table_lineage_edges = [
            RawLineage(
                source_urn=edge.source_urn,
                target_urn=table_entities[mapping.dataset_name].urn,
                relationship=RelationshipType.DERIVED_FROM,
                level=LineageLevel.TABLE,
                method=edge.method,
                confidence=edge.confidence,
                evidence=edge.evidence,
            )
            for mapping, edge in ((mapping, edge) for mapping in mappings for edge in lineage_edges)
            if mapping.dataset_name in table_entities
            and edge.evidence.get("business_term") == mapping.business_term
        ]
        lineage_edges.extend(table_lineage_edges)

        # Workbook-style uploads describe relationships through named sheets. Preserve those
        # structural links even when no glossary term was confidently mapped.
        sheet_relationships = (
            ("documentation_artifacts", "doc_column_mappings"),
            ("doc_column_mappings", "columns"),
            ("datasets", "columns"),
            ("source_systems", "datasets"),
        )
        for source_name, target_name in sheet_relationships:
            source = table_entities.get(source_name)
            target = table_entities.get(target_name)
            if source is None or target is None:
                continue
            lineage_edges.append(
                RawLineage(
                    source_urn=source.urn,
                    target_urn=target.urn,
                    relationship=RelationshipType.REFERENCES,
                    level=LineageLevel.TABLE,
                    method=LineageMethod.CONNECTOR_DECLARED,
                    confidence=0.85,
                    evidence={
                        "source": "enrichment_workbook_structure",
                        "run_id": str(run.id),
                        "relationship": f"{source_name} references {target_name}",
                    },
                )
            )

        if lineage_edges:
            await LineageService(self.session).persist_edges(
                lineage_edges, principal=principal, create_missing_entities=False
            )

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
