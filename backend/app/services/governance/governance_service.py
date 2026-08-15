"""Governance application service: ownership, classification and policy in one view."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ClassificationLevel, OwnershipRole, SensitivityTag
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.repositories.governance_repository import GovernanceRepository
from app.repositories.metadata_repository import MetadataRepository
from app.schemas.governance import (
    ClassificationRead,
    EntityClassificationRead,
    GovernanceProfile,
    OwnerCreate,
    OwnerRead,
    OwnershipAssignment,
    OwnershipRead,
    PolicyRead,
    SensitiveAssetsQuery,
)
from app.services.governance.classification_service import ClassificationService
from app.services.governance.policy_service import PolicyService

logger = get_logger(__name__)

_LEVEL_ORDER = {
    ClassificationLevel.PUBLIC: 0,
    ClassificationLevel.INTERNAL: 1,
    ClassificationLevel.CONFIDENTIAL: 2,
    ClassificationLevel.RESTRICTED: 3,
}


class GovernanceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = GovernanceRepository(session)
        self.metadata_repo = MetadataRepository(session)
        self.classification = ClassificationService(session)
        self.policy = PolicyService(session)

    # ------------------------------------------------------------------ #
    # Profile
    # ------------------------------------------------------------------ #
    async def get_profile(self, urn: str) -> GovernanceProfile:
        """Everything a steward needs about one asset."""
        entity = await self.repo.entity_with_governance(urn)
        if entity is None:
            raise NotFoundError(f"No catalog entity with URN '{urn}'.")

        owners = [
            OwnershipRead(
                role=assignment.role, owner=OwnerRead.model_validate(assignment.owner)
            )
            for assignment in entity.owners
        ]
        classifications = [
            EntityClassificationRead(
                classification=ClassificationRead.model_validate(assignment.classification),
                method=assignment.method,
                confidence=assignment.confidence,
                confirmed=assignment.confirmed,
                evidence=assignment.evidence,
            )
            for assignment in entity.classifications
        ]

        sensitivities = {item.classification.sensitivity for item in classifications}
        levels = {item.classification.level for item in classifications}
        highest_level = max(levels, key=lambda level: _LEVEL_ORDER[level], default=ClassificationLevel.INTERNAL)

        policies = await self.policy.applicable_policies(
            entity, sensitivities=sensitivities, levels=levels
        )

        notes: list[str] = []
        if not owners:
            notes.append("No accountable owner is assigned to this asset.")
        if SensitivityTag.PII in sensitivities:
            notes.append("Contains personal data: access requires an approved request.")
        unconfirmed = [item for item in classifications if not item.confirmed]
        if unconfirmed:
            notes.append(
                f"{len(unconfirmed)} classification(s) are suggested but not yet confirmed by a steward."
            )

        return GovernanceProfile(
            entity_urn=entity.urn,
            entity_name=entity.qualified_name,
            owners=owners,
            classifications=classifications,
            highest_sensitivity=(
                SensitivityTag.PII
                if SensitivityTag.PII in sensitivities
                else next(iter(sensitivities - {SensitivityTag.NONE}), SensitivityTag.NONE)
            ),
            classification_level=highest_level,
            applicable_policies=[PolicyRead.model_validate(policy) for policy in policies],
            contains_pii=SensitivityTag.PII in sensitivities,
            unowned=not owners,
            compliance_notes=notes,
        )

    # ------------------------------------------------------------------ #
    # Ownership
    # ------------------------------------------------------------------ #
    async def create_owner(self, payload: OwnerCreate) -> OwnerRead:
        owner = await self.repo.upsert_owner(
            payload.name,
            email=str(payload.email) if payload.email else None,
            owner_type=payload.owner_type,
            department=payload.department,
            external_id=payload.external_id,
        )
        return OwnerRead.model_validate(owner)

    async def list_owners(self) -> list[OwnerRead]:
        return [OwnerRead.model_validate(owner) for owner in await self.repo.list_owners()]

    async def assign_owner(
        self, payload: OwnershipAssignment, *, principal: str
    ) -> OwnershipRead:
        entity = await self.metadata_repo.get_by_urn(payload.entity_urn)
        if entity is None:
            raise NotFoundError(f"No catalog entity with URN '{payload.entity_urn}'.")

        owner_id = payload.owner_id
        if owner_id is None:
            if not payload.owner_name:
                raise NotFoundError("Either owner_id or owner_name must be provided.")
            owner = await self.repo.upsert_owner(payload.owner_name)
            owner_id = owner.id

        assignment = await self.repo.assign_owner(
            entity.id, owner_id, payload.role, assigned_by=principal
        )
        return OwnershipRead(
            role=assignment.role, owner=OwnerRead.model_validate(assignment.owner)
        )

    async def assign_owner_by_name(
        self, entity_id: uuid.UUID, owner_name: str, role: OwnershipRole, *, principal: str
    ) -> None:
        """Used by ingestion when a connector declares ownership."""
        owner = await self.repo.upsert_owner(owner_name)
        await self.repo.assign_owner(entity_id, owner.id, role, assigned_by=principal)

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #
    async def sensitive_assets(self, query: SensitiveAssetsQuery) -> list[dict[str, object]]:
        """Answers "which datasets contain PII?"."""
        rows = await self.repo.find_entities_by_sensitivity(
            query.sensitivity, platform=query.platform, limit=query.limit
        )
        return [
            {
                "urn": entity.urn,
                "qualified_name": entity.qualified_name,
                "entity_type": entity.entity_type.value,
                "platform": entity.platform,
                "classification": classification.name,
                "level": classification.level.value,
                "regulation": classification.regulation,
            }
            for entity, classification in rows
        ]

    async def unowned_assets(self, *, limit: int = 50) -> list[dict[str, str]]:
        """Governance gap report."""
        return [
            {
                "urn": entity.urn,
                "qualified_name": entity.qualified_name,
                "entity_type": entity.entity_type.value,
                "platform": entity.platform,
            }
            for entity in await self.repo.unowned_entities(limit=limit)
        ]

    async def bootstrap(self) -> None:
        """Ensure baseline classifications and policies exist."""
        await self.classification.ensure_definitions()
        await self.policy.seed_defaults()
