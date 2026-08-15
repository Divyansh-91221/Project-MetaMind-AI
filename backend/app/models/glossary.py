"""Business glossary models: terms, KPIs and their links to technical assets."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.metadata import MetadataEntity


class BusinessTerm(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A governed business definition ("Customer Revenue", "Active Customer")."""

    __tablename__ = "business_terms"
    __table_args__ = (
        UniqueConstraint("name", "domain", name="uq_business_terms_name_domain"),
        Index("ix_business_terms_name", "name"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(128), nullable=False, default="enterprise")
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    short_description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    synonyms: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    abbreviation: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # KPI-specific attributes; populated when ``is_kpi`` is true.
    is_kpi: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    calculation: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="APPROVED")
    steward: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parent_term_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("business_terms.id", ondelete="SET NULL"), nullable=True
    )
    properties: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    assignments: Mapped[list[TermAssignment]] = relationship(
        back_populates="term", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<BusinessTerm {self.name}{' (KPI)' if self.is_kpi else ''}>"


class TermAssignment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Links a business term to a technical asset - the business-context bridge."""

    __tablename__ = "term_assignments"
    __table_args__ = (
        UniqueConstraint("term_id", "entity_id", name="uq_term_assignments_identity"),
        Index("ix_term_assignments_entity", "entity_id"),
    )

    term_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("business_terms.id", ondelete="CASCADE"), nullable=False
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("metadata_entities.id", ondelete="CASCADE"), nullable=False
    )
    # MANUAL | RULE | AI_SUGGESTED
    method: Mapped[str] = mapped_column(String(32), nullable=False, default="MANUAL")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    term: Mapped[BusinessTerm] = relationship(back_populates="assignments", lazy="joined")
    entity: Mapped[MetadataEntity] = relationship(lazy="joined")
