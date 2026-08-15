"""Lexical catalog search.

Exact and substring matching over names, qualified names and descriptions. This is the half
of hybrid search that reliably finds identifiers such as ``customer_id`` - embeddings tend to
blur those.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import EntityType
from app.models.metadata import MetadataEntity
from app.repositories.metadata_repository import MetadataRepository
from app.schemas.search import SearchHit
from app.utils.serialization import truncate


class MetadataSearch:
    """Keyword search over the catalog."""

    def __init__(self, session: AsyncSession) -> None:
        self.repo = MetadataRepository(session)

    async def search(
        self,
        query: str,
        *,
        entity_types: list[EntityType] | None = None,
        platforms: list[str] | None = None,
        limit: int = 20,
    ) -> list[SearchHit]:
        rows = await self.repo.keyword_search(
            query, entity_types=entity_types, platforms=platforms, limit=limit
        )
        return [self._to_hit(row, query) for row in rows]

    @staticmethod
    def _to_hit(entity: MetadataEntity, query: str) -> SearchHit:
        lowered = query.lower().strip()
        name = entity.name.lower()
        qualified = entity.qualified_name.lower()
        description = (entity.description or "").lower()

        if name == lowered:
            score, matched_on = 1.0, ["name"]
        elif qualified == lowered:
            score, matched_on = 1.0, ["qualified_name"]
        elif qualified.endswith(f".{lowered}"):
            score, matched_on = 0.9, ["qualified_name"]
        elif lowered in name:
            score, matched_on = 0.75, ["name"]
        elif lowered in qualified:
            score, matched_on = 0.6, ["qualified_name"]
        elif lowered in description:
            score, matched_on = 0.45, ["description"]
        else:
            score, matched_on = 0.3, ["fuzzy"]

        highlights = (
            [truncate(entity.description or "", 200)] if entity.description and lowered in description else []
        )

        return SearchHit(
            urn=entity.urn,
            name=entity.name,
            qualified_name=entity.qualified_name,
            entity_type=entity.entity_type,
            platform=entity.platform,
            description=entity.description,
            score=round(score, 4),
            keyword_score=round(score, 4),
            matched_on=matched_on,
            highlights=highlights,
        )
