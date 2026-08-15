"""Data access for governance: owners, classifications and policies."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.core.constants import OwnershipRole, SensitivityTag
from app.models.governance import (
    Classification,
    EntityClassification,
    EntityOwner,
    Owner,
    Policy,
)
from app.models.metadata import MetadataEntity


class GovernanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------ #
    # Owners
    # ------------------------------------------------------------------ #
    async def get_owner_by_name(self, name: str) -> Owner | None:
        stmt = select(Owner).where(Owner.name == name)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def upsert_owner(self, name: str, **values: Any) -> Owner:
        owner = await self.get_owner_by_name(name)
        if owner is None:
            owner = Owner(name=name, **values)
            self.session.add(owner)
        else:
            for key, value in values.items():
                if value is not None:
                    setattr(owner, key, value)
        await self.session.flush()
        return owner

    async def list_owners(self) -> list[Owner]:
        return list((await self.session.execute(select(Owner).order_by(Owner.name))).scalars().all())

    async def owners_for_entity(self, entity_id: uuid.UUID) -> list[EntityOwner]:
        stmt = (
            select(EntityOwner)
            .where(EntityOwner.entity_id == entity_id)
            .options(joinedload(EntityOwner.owner))
        )
        return list((await self.session.execute(stmt)).unique().scalars().all())

    async def owners_for_entities(self, entity_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        """Bulk owner lookup - used by impact analysis to build the notification list."""
        if not entity_ids:
            return {}
        stmt = (
            select(EntityOwner)
            .where(EntityOwner.entity_id.in_(entity_ids))
            .options(joinedload(EntityOwner.owner))
        )
        mapping: dict[uuid.UUID, list[str]] = {}
        for assignment in (await self.session.execute(stmt)).unique().scalars().all():
            mapping.setdefault(assignment.entity_id, []).append(assignment.owner.name)
        return mapping

    async def assign_owner(
        self, entity_id: uuid.UUID, owner_id: uuid.UUID, role: OwnershipRole, assigned_by: str
    ) -> EntityOwner:
        stmt = select(EntityOwner).where(
            EntityOwner.entity_id == entity_id,
            EntityOwner.owner_id == owner_id,
            EntityOwner.role == role,
        )
        existing = (await self.session.execute(stmt)).unique().scalar_one_or_none()
        if existing is not None:
            return existing
        assignment = EntityOwner(
            entity_id=entity_id, owner_id=owner_id, role=role, assigned_by=assigned_by
        )
        self.session.add(assignment)
        await self.session.flush()
        return assignment

    # ------------------------------------------------------------------ #
    # Classifications
    # ------------------------------------------------------------------ #
    async def get_classification(self, name: str) -> Classification | None:
        stmt = select(Classification).where(Classification.name == name)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def upsert_classification(self, name: str, **values: Any) -> Classification:
        classification = await self.get_classification(name)
        if classification is None:
            classification = Classification(name=name, **values)
            self.session.add(classification)
        else:
            for key, value in values.items():
                if value is not None:
                    setattr(classification, key, value)
        await self.session.flush()
        return classification

    async def list_classifications(self) -> list[Classification]:
        stmt = select(Classification).order_by(Classification.name)
        return list((await self.session.execute(stmt)).scalars().all())

    async def classifications_for_entity(self, entity_id: uuid.UUID) -> list[EntityClassification]:
        stmt = (
            select(EntityClassification)
            .where(EntityClassification.entity_id == entity_id)
            .options(joinedload(EntityClassification.classification))
        )
        return list((await self.session.execute(stmt)).unique().scalars().all())

    async def assign_classification(
        self,
        entity_id: uuid.UUID,
        classification_id: uuid.UUID,
        *,
        method: str = "MANUAL",
        confidence: float = 1.0,
        confirmed: bool = True,
        assigned_by: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> EntityClassification:
        stmt = select(EntityClassification).where(
            EntityClassification.entity_id == entity_id,
            EntityClassification.classification_id == classification_id,
        )
        existing = (await self.session.execute(stmt)).unique().scalar_one_or_none()
        if existing is not None:
            existing.method = method
            existing.confidence = confidence
            existing.confirmed = confirmed or existing.confirmed
            await self.session.flush()
            return existing

        assignment = EntityClassification(
            entity_id=entity_id,
            classification_id=classification_id,
            method=method,
            confidence=confidence,
            confirmed=confirmed,
            assigned_by=assigned_by,
            evidence=evidence or {},
        )
        self.session.add(assignment)
        await self.session.flush()
        return assignment

    async def find_entities_by_sensitivity(
        self, sensitivity: SensitivityTag, *, platform: str | None = None, limit: int = 50
    ) -> list[tuple[MetadataEntity, Classification]]:
        """Answers "which datasets contain PII?"."""
        stmt = (
            select(MetadataEntity, Classification)
            .join(EntityClassification, EntityClassification.entity_id == MetadataEntity.id)
            .join(Classification, Classification.id == EntityClassification.classification_id)
            .where(
                Classification.sensitivity == sensitivity,
                MetadataEntity.deleted_at.is_(None),
            )
            .order_by(MetadataEntity.qualified_name)
            .limit(limit)
        )
        if platform:
            stmt = stmt.where(MetadataEntity.platform == platform)
        return [(row[0], row[1]) for row in (await self.session.execute(stmt)).all()]

    async def unowned_entities(self, *, limit: int = 50) -> list[MetadataEntity]:
        """Governance gap report: assets without any accountable owner."""
        owned = select(EntityOwner.entity_id).distinct()
        stmt = (
            select(MetadataEntity)
            .where(
                MetadataEntity.deleted_at.is_(None),
                MetadataEntity.id.not_in(owned),
                MetadataEntity.entity_type.in_(["TABLE", "DATASET", "DASHBOARD", "REPORT"]),
            )
            .order_by(MetadataEntity.qualified_name)
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    # ------------------------------------------------------------------ #
    # Policies
    # ------------------------------------------------------------------ #
    async def list_policies(self, *, active_only: bool = True) -> list[Policy]:
        stmt = select(Policy).order_by(Policy.name)
        if active_only:
            stmt = stmt.where(Policy.active.is_(True))
        return list((await self.session.execute(stmt)).scalars().all())

    async def upsert_policy(self, name: str, **values: Any) -> Policy:
        stmt = select(Policy).where(Policy.name == name)
        policy = (await self.session.execute(stmt)).scalar_one_or_none()
        if policy is None:
            policy = Policy(name=name, **values)
            self.session.add(policy)
        else:
            for key, value in values.items():
                if value is not None:
                    setattr(policy, key, value)
        await self.session.flush()
        return policy

    async def entity_with_governance(self, urn: str) -> MetadataEntity | None:
        stmt = (
            select(MetadataEntity)
            .where(MetadataEntity.urn == urn)
            .options(
                selectinload(MetadataEntity.owners).joinedload(EntityOwner.owner),
                selectinload(MetadataEntity.classifications).joinedload(
                    EntityClassification.classification
                ),
            )
        )
        return (await self.session.execute(stmt)).unique().scalar_one_or_none()
