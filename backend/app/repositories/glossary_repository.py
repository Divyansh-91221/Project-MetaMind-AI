"""Data access for the business glossary."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.glossary import BusinessTerm, TermAssignment


class GlossaryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_name(self, name: str, *, domain: str | None = None) -> BusinessTerm | None:
        stmt = select(BusinessTerm).where(func.lower(BusinessTerm.name) == name.lower().strip())
        if domain:
            stmt = stmt.where(BusinessTerm.domain == domain)
        return (await self.session.execute(stmt)).scalars().first()

    async def search(self, query: str, *, limit: int = 20) -> list[BusinessTerm]:
        """Match on name, synonyms, abbreviation or definition text."""
        pattern = f"%{query.lower().strip()}%"
        stmt = (
            select(BusinessTerm)
            .where(
                or_(
                    func.lower(BusinessTerm.name).like(pattern),
                    func.lower(func.coalesce(BusinessTerm.abbreviation, "")).like(pattern),
                    func.lower(BusinessTerm.definition).like(pattern),
                    BusinessTerm.synonyms.contains([query.lower().strip()]),
                )
            )
            .order_by((func.lower(BusinessTerm.name) == query.lower().strip()).desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_terms(
        self, *, kpi_only: bool = False, limit: int = 100, offset: int = 0
    ) -> tuple[list[BusinessTerm], int]:
        base = select(BusinessTerm)
        if kpi_only:
            base = base.where(BusinessTerm.is_kpi.is_(True))
        total = int(
            (await self.session.execute(select(func.count()).select_from(base.subquery())))
            .scalar_one()
        )
        stmt = base.order_by(BusinessTerm.name).limit(limit).offset(offset)
        return list((await self.session.execute(stmt)).scalars().all()), total

    async def upsert_term(self, name: str, domain: str, **values: Any) -> BusinessTerm:
        stmt = select(BusinessTerm).where(
            BusinessTerm.name == name, BusinessTerm.domain == domain
        )
        term = (await self.session.execute(stmt)).scalar_one_or_none()
        if term is None:
            term = BusinessTerm(name=name, domain=domain, **values)
            self.session.add(term)
        else:
            for key, value in values.items():
                if value is not None:
                    setattr(term, key, value)
        await self.session.flush()
        return term

    async def assignments_for_term(self, term_id: uuid.UUID) -> list[TermAssignment]:
        stmt = (
            select(TermAssignment)
            .where(TermAssignment.term_id == term_id)
            .options(joinedload(TermAssignment.entity))
        )
        return list((await self.session.execute(stmt)).unique().scalars().all())

    async def terms_for_entity(self, entity_id: uuid.UUID) -> list[TermAssignment]:
        stmt = (
            select(TermAssignment)
            .where(TermAssignment.entity_id == entity_id)
            .options(joinedload(TermAssignment.term))
        )
        return list((await self.session.execute(stmt)).unique().scalars().all())

    async def assign_term(
        self,
        term_id: uuid.UUID,
        entity_id: uuid.UUID,
        *,
        method: str = "MANUAL",
        confidence: float = 1.0,
        confirmed: bool = True,
    ) -> TermAssignment:
        stmt = select(TermAssignment).where(
            TermAssignment.term_id == term_id, TermAssignment.entity_id == entity_id
        )
        existing = (await self.session.execute(stmt)).unique().scalar_one_or_none()
        if existing is not None:
            return existing
        assignment = TermAssignment(
            term_id=term_id,
            entity_id=entity_id,
            method=method,
            confidence=confidence,
            confirmed=confirmed,
        )
        self.session.add(assignment)
        await self.session.flush()
        return assignment
