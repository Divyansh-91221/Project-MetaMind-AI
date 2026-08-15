"""Metadata ingestion processor.

Consumes a connector's entity stream and writes it to the catalog. Responsibilities:

* order records so containers exist before their children,
* resolve parent references to primary keys,
* apply connector-declared ownership, classification and glossary links,
* run rule-based classification on new columns.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import RawEntity
from app.core.constants import OwnershipRole
from app.core.logging import get_logger
from app.services.glossary.glossary_service import GlossaryService
from app.services.governance.classification_service import ClassificationService
from app.services.governance.governance_service import GovernanceService
from app.services.metadata.metadata_normalizer import metadata_normalizer
from app.services.metadata.metadata_service import MetadataService

logger = get_logger(__name__)


@dataclass(slots=True)
class MetadataProcessingResult:
    created: int = 0
    updated: int = 0
    urn_to_id: dict[str, uuid.UUID] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class MetadataProcessor:
    """Persists connector entity records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.metadata = MetadataService(session)
        self.governance = GovernanceService(session)
        self.classification = ClassificationService(session)
        self.glossary = GlossaryService(session)

    async def process(
        self,
        entities: list[RawEntity],
        *,
        data_source_id: uuid.UUID | None = None,
        principal: str = "system",
        classify: bool = True,
    ) -> MetadataProcessingResult:
        result = MetadataProcessingResult()
        await self.classification.ensure_definitions()

        # Containers first so every parent reference resolves in a single pass.
        for raw in sorted(entities, key=metadata_normalizer.sort_key):
            try:
                parent_urn = metadata_normalizer.parent_urn_for(raw)
                parent_id = result.urn_to_id.get(parent_urn) if parent_urn else None
                if parent_urn and parent_id is None:
                    existing_parent = await self.metadata.repo.get_by_urn(parent_urn)
                    parent_id = existing_parent.id if existing_parent else None

                entity, created = await self.metadata.upsert_raw_entity(
                    raw, data_source_id=data_source_id, parent_id=parent_id
                )
                result.urn_to_id[entity.urn] = entity.id
                result.created += int(created)
                result.updated += int(not created)

                await self._apply_context(raw, entity.id, principal=principal)
                if classify:
                    await self.classification.apply(entity, principal=principal)
            except Exception as exc:  # noqa: BLE001 - one bad record must not fail the run
                message = f"{raw.entity_type.value} {raw.qualified_name}: {exc}"
                result.errors.append(message)
                logger.warning("entity_ingestion_failed", extra={"error": message})

        logger.info(
            "metadata_processing_completed",
            extra={
                "created": result.created,
                "updated": result.updated,
                "errors": len(result.errors),
            },
        )
        return result

    async def _apply_context(
        self, raw: RawEntity, entity_id: uuid.UUID, *, principal: str
    ) -> None:
        """Apply ownership, classification and glossary links declared by the connector."""
        for owner_name, role in raw.owners:
            try:
                ownership_role = OwnershipRole(role)
            except ValueError:
                ownership_role = OwnershipRole.DATA_OWNER
            await self.governance.assign_owner_by_name(
                entity_id, owner_name, ownership_role, principal=principal
            )

        for classification_name in raw.classifications:
            await self.classification.assign_named(
                entity_id,
                classification_name,
                method="CONNECTOR",
                confidence=0.9,
                confirmed=False,
                principal=principal,
            )

        for term_name in raw.business_terms:
            await self.glossary.link_term_by_name(term_name, entity_id)
