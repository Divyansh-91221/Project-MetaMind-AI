"""Metadata catalog application service."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import RawEntity
from app.core.constants import AuditAction, EntityType
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models.metadata import MetadataEntity
from app.repositories.audit_repository import AuditRepository
from app.repositories.glossary_repository import GlossaryRepository
from app.repositories.governance_repository import GovernanceRepository
from app.repositories.lineage_repository import LineageRepository
from app.repositories.metadata_repository import MetadataRepository
from app.repositories.quality_repository import QualityRepository
from app.schemas.common import Page
from app.schemas.metadata import (
    ColumnSummary,
    MetadataEntityDetail,
    MetadataEntityRead,
    MetadataEntityUpdate,
    MetadataFilter,
)
from app.services.metadata.metadata_normalizer import metadata_normalizer
from app.utils.timestamps import age_hours

logger = get_logger(__name__)


class MetadataService:
    """Read/write operations over the catalog. Used by the API, ingestion and the agent."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = MetadataRepository(session)
        self.lineage_repo = LineageRepository(session)
        self.governance_repo = GovernanceRepository(session)
        self.glossary_repo = GlossaryRepository(session)
        self.quality_repo = QualityRepository(session)
        self.audit_repo = AuditRepository(session)

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    async def list_entities(
        self, filters: MetadataFilter, *, limit: int = 50, offset: int = 0
    ) -> Page[MetadataEntityRead]:
        parent_id: uuid.UUID | None = None
        if filters.parent_urn:
            parent = await self.repo.get_by_urn(filters.parent_urn)
            if parent is None:
                raise NotFoundError(f"Parent entity '{filters.parent_urn}' was not found.")
            parent_id = parent.id

        rows, total = await self.repo.list_entities(
            entity_type=filters.entity_type,
            platform=filters.platform,
            parent_id=parent_id,
            search=filters.search,
            tag=filters.tag,
            include_deleted=filters.include_deleted,
            limit=limit,
            offset=offset,
        )
        return Page[MetadataEntityRead](
            items=[MetadataEntityRead.model_validate(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_entity(self, urn: str) -> MetadataEntity:
        entity = await self.repo.get_by_urn(urn)
        if entity is None:
            raise NotFoundError(f"No catalog entity with URN '{urn}'.")
        return entity

    async def get_entity_detail(self, urn: str) -> MetadataEntityDetail:
        """Assemble the full asset view: technical + business + governance + quality."""
        entity = await self.repo.get_detail_by_urn(urn)
        if entity is None:
            raise NotFoundError(f"No catalog entity with URN '{urn}'.")

        detail = MetadataEntityDetail.model_validate(entity)
        detail.parent_urn = entity.parent.urn if entity.parent else None

        columns = [child for child in entity.children if child.entity_type is EntityType.COLUMN]
        column_classifications = {
            column.id: [
                assignment.classification.name
                for assignment in await self.governance_repo.classifications_for_entity(column.id)
            ]
            for column in columns
        }
        detail.columns = [
            ColumnSummary(
                urn=column.urn,
                name=column.name,
                data_type=column.data_type,
                ordinal_position=column.ordinal_position,
                is_nullable=column.is_nullable,
                is_primary_key=column.is_primary_key,
                description=column.description,
                classifications=column_classifications.get(column.id, []),
            )
            for column in sorted(columns, key=lambda c: (c.ordinal_position or 0, c.name))
        ]

        detail.owners = [
            {"name": assignment.owner.name, "role": assignment.role.value,
             "email": assignment.owner.email}
            for assignment in await self.governance_repo.owners_for_entity(entity.id)
        ]
        detail.classifications = [
            {
                "name": assignment.classification.name,
                "level": assignment.classification.level.value,
                "sensitivity": assignment.classification.sensitivity.value,
                "method": assignment.method,
                "confirmed": assignment.confirmed,
            }
            for assignment in await self.governance_repo.classifications_for_entity(entity.id)
        ]
        detail.business_terms = [
            {
                "name": assignment.term.name,
                "definition": assignment.term.definition,
                "is_kpi": assignment.term.is_kpi,
            }
            for assignment in await self.glossary_repo.terms_for_entity(entity.id)
        ]

        freshness = await self.quality_repo.get_freshness(entity.id)
        if freshness is not None:
            detail.quality = {
                "status": freshness.status.value,
                "last_updated_at": freshness.last_updated_at,
                "age_hours": age_hours(freshness.last_updated_at),
                "expected_interval_hours": freshness.expected_interval_hours,
                "failure_reason": freshness.failure_reason,
            }

        upstream, downstream = await self.lineage_repo.count_neighbours(entity.id)
        detail.upstream_count = upstream
        detail.downstream_count = downstream
        return detail

    async def get_columns(self, table_urn: str) -> list[MetadataEntityRead]:
        entity = await self.get_entity(table_urn)
        children = await self.repo.get_children(entity.id, EntityType.COLUMN)
        return [MetadataEntityRead.model_validate(child) for child in children]

    async def catalog_summary(self) -> dict[str, Any]:
        """Dashboard counters."""
        lineage_stats = await self.lineage_repo.stats()
        return {
            "entities_by_type": await self.repo.count_by_type(),
            "entities_by_platform": await self.repo.count_by_platform(),
            "lineage": lineage_stats,
            "data_sources": len(await self.repo.list_data_sources()),
        }

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #
    async def upsert_raw_entity(
        self,
        raw: RawEntity,
        *,
        data_source_id: uuid.UUID | None = None,
        parent_id: uuid.UUID | None = None,
    ) -> tuple[MetadataEntity, bool]:
        """Normalise and persist one connector record."""
        values = metadata_normalizer.normalize(
            raw, data_source_id=data_source_id, parent_id=parent_id
        )
        return await self.repo.upsert(values)

    async def update_entity(
        self, urn: str, payload: MetadataEntityUpdate, *, principal: str
    ) -> MetadataEntityRead:
        """Curated edits (description, tags, deprecation) made by a steward."""
        entity = await self.get_entity(urn)
        changes = payload.model_dump(exclude_unset=True)
        await self.repo.update_curated_fields(entity, changes)
        await self.audit_repo.record(
            AuditAction.ENTITY_UPDATED,
            principal=principal,
            entity_id=entity.id,
            entity_urn=entity.urn,
            resource_type="metadata_entity",
            summary=f"Updated {', '.join(changes)} on {entity.qualified_name}.",
            payload=changes,
        )
        return MetadataEntityRead.model_validate(entity)

    async def ensure_entity(
        self, *, urn: str, entity_type: EntityType, platform: str, qualified_name: str
    ) -> MetadataEntity:
        """Get or create a minimal entity - used when lineage references unknown assets."""
        existing = await self.repo.get_by_urn(urn)
        if existing is not None:
            return existing
        entity, _ = await self.repo.upsert(
            {
                "urn": urn,
                "entity_type": entity_type,
                "platform": platform,
                "name": qualified_name.split(".")[-1],
                "qualified_name": qualified_name,
                "properties": {"placeholder": True},
            }
        )
        return entity
