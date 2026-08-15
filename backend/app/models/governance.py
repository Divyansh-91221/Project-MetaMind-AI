"""Governance models: ownership, classification and policy."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import ClassificationLevel, OwnershipRole, SensitivityTag
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.metadata import MetadataEntity


class Owner(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A person or team accountable for data assets.

    ``external_id`` is the identity-provider subject, so this maps cleanly onto SSO later.
    """

    __tablename__ = "owners"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    owner_type: Mapped[str] = mapped_column(String(32), nullable=False, default="TEAM")
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    properties: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    assignments: Mapped[list[EntityOwner]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class EntityOwner(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Ownership assignment between an asset and an owner, scoped by role."""

    __tablename__ = "entity_owners"
    __table_args__ = (
        UniqueConstraint("entity_id", "owner_id", "role", name="uq_entity_owners_identity"),
        Index("ix_entity_owners_entity", "entity_id"),
    )

    entity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("metadata_entities.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("owners.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[OwnershipRole] = mapped_column(
        SAEnum(OwnershipRole, name="ownership_role"),
        nullable=False,
        default=OwnershipRole.DATA_OWNER,
    )
    assigned_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    entity: Mapped[MetadataEntity] = relationship(back_populates="owners")
    owner: Mapped[Owner] = relationship(back_populates="assignments", lazy="joined")


class Classification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A reusable sensitivity/classification definition (e.g. ``PII.Email``)."""

    __tablename__ = "classifications"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    level: Mapped[ClassificationLevel] = mapped_column(
        SAEnum(ClassificationLevel, name="classification_level"),
        nullable=False,
        default=ClassificationLevel.INTERNAL,
    )
    sensitivity: Mapped[SensitivityTag] = mapped_column(
        SAEnum(SensitivityTag, name="sensitivity_tag"),
        nullable=False,
        default=SensitivityTag.NONE,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    regulation: Mapped[str | None] = mapped_column(String(128), nullable=True)

    assignments: Mapped[list[EntityClassification]] = relationship(
        back_populates="classification", cascade="all, delete-orphan"
    )


class EntityClassification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Applies a classification to an asset, tracking how it was determined."""

    __tablename__ = "entity_classifications"
    __table_args__ = (
        UniqueConstraint(
            "entity_id", "classification_id", name="uq_entity_classifications_identity"
        ),
        Index("ix_entity_classifications_entity", "entity_id"),
    )

    entity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("metadata_entities.id", ondelete="CASCADE"), nullable=False
    )
    classification_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("classifications.id", ondelete="CASCADE"), nullable=False
    )
    # RULE | MANUAL | AI_SUGGESTED - AI suggestions stay unconfirmed until reviewed.
    method: Mapped[str] = mapped_column(String(32), nullable=False, default="MANUAL")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    assigned_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    entity: Mapped[MetadataEntity] = relationship(back_populates="classifications")
    classification: Mapped[Classification] = relationship(
        back_populates="assignments", lazy="joined"
    )


class Policy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A governance policy (retention, access, masking, quality SLA).

    ``rule`` holds a declarative payload evaluated by :mod:`app.services.governance.policy_service`.
    TODO: replace the JSON rule with a versioned policy DSL and an evaluation audit trail.
    """

    __tablename__ = "policies"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    policy_type: Mapped[str] = mapped_column(String(64), nullable=False, default="ACCESS")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    enforcement: Mapped[str] = mapped_column(String(32), nullable=False, default="ADVISORY")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("owners.id", ondelete="SET NULL"), nullable=True
    )
