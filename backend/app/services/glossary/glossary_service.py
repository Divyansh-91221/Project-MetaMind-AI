"""Business glossary service - the bridge between business language and technical assets."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.repositories.glossary_repository import GlossaryRepository
from app.repositories.metadata_repository import MetadataRepository
from app.schemas.common import Page
from app.schemas.glossary import (
    BusinessTermCreate,
    BusinessTermDetail,
    BusinessTermRead,
    LinkedAsset,
    TermAssignmentRequest,
)

logger = get_logger(__name__)


class GlossaryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = GlossaryRepository(session)
        self.metadata_repo = MetadataRepository(session)

    async def list_terms(
        self, *, kpi_only: bool = False, limit: int = 50, offset: int = 0
    ) -> Page[BusinessTermRead]:
        terms, total = await self.repo.list_terms(kpi_only=kpi_only, limit=limit, offset=offset)
        return Page[BusinessTermRead](
            items=[BusinessTermRead.model_validate(term) for term in terms],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_term(self, name: str) -> BusinessTermDetail:
        """Resolve a term by exact name, then by synonym/definition search."""
        term = await self.repo.get_by_name(name)
        if term is None:
            candidates = await self.repo.search(name, limit=1)
            term = candidates[0] if candidates else None
        if term is None:
            raise NotFoundError(f"No business term matching '{name}'.")

        assignments = await self.repo.assignments_for_term(term.id)
        detail = BusinessTermDetail.model_validate(term)
        detail.linked_assets = [
            LinkedAsset(
                urn=assignment.entity.urn,
                name=assignment.entity.name,
                qualified_name=assignment.entity.qualified_name,
                entity_type=assignment.entity.entity_type.value,
                platform=assignment.entity.platform,
                method=assignment.method,
                confidence=assignment.confidence,
            )
            for assignment in assignments
        ]
        return detail

    async def search(self, query: str, *, limit: int = 20) -> list[BusinessTermRead]:
        terms = await self.repo.search(query, limit=limit)
        return [BusinessTermRead.model_validate(term) for term in terms]

    async def create_term(self, payload: BusinessTermCreate) -> BusinessTermRead:
        term = await self.repo.upsert_term(
            payload.name,
            payload.domain,
            definition=payload.definition,
            short_description=payload.short_description,
            synonyms=payload.synonyms,
            abbreviation=payload.abbreviation,
            is_kpi=payload.is_kpi,
            calculation=payload.calculation,
            unit=payload.unit,
            status=payload.status,
            steward=payload.steward,
        )
        for urn in payload.linked_entity_urns:
            entity = await self.metadata_repo.get_by_urn(urn)
            if entity is None:
                logger.warning("glossary_link_skipped_unknown_entity", extra={"urn": urn})
                continue
            await self.repo.assign_term(term.id, entity.id)
        return BusinessTermRead.model_validate(term)

    async def assign_term(self, payload: TermAssignmentRequest) -> None:
        term = await self.repo.get_by_name(payload.term_name)
        if term is None:
            raise NotFoundError(f"No business term named '{payload.term_name}'.")
        entity = await self.metadata_repo.get_by_urn(payload.entity_urn)
        if entity is None:
            raise NotFoundError(f"No catalog entity with URN '{payload.entity_urn}'.")
        await self.repo.assign_term(
            term.id,
            entity.id,
            method=payload.method,
            confidence=payload.confidence,
            confirmed=payload.method == "MANUAL",
        )

    async def link_term_by_name(self, term_name: str, entity_id: object) -> None:
        """Used by ingestion when a connector declares a business term on a column."""
        term = await self.repo.get_by_name(term_name)
        if term is None:
            logger.debug("glossary_term_missing_during_ingestion", extra={"term": term_name})
            return
        await self.repo.assign_term(term.id, entity_id, method="CONNECTOR", confirmed=False)  # type: ignore[arg-type]
