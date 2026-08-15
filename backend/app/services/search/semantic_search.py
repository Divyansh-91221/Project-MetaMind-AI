"""Semantic catalog search.

Runs the natural-language query through the RAG retriever and maps the resulting chunks back
onto catalog entities. Chunks without an ``entity_urn`` (policies, architecture docs) are
returned separately as document evidence rather than being forced into asset results.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import EntityType
from app.core.logging import get_logger
from app.rag.rag_pipeline import RAGPipeline
from app.repositories.metadata_repository import MetadataRepository
from app.schemas.search import DocumentHit, SearchHit
from app.utils.serialization import truncate

logger = get_logger(__name__)


class SemanticSearch:
    """Embedding-based search over indexed catalog descriptions and documentation."""

    def __init__(self, session: AsyncSession, pipeline: RAGPipeline | None = None) -> None:
        self.session = session
        self.pipeline = pipeline or RAGPipeline(session)
        self.repo = MetadataRepository(session)

    async def search(
        self,
        query: str,
        *,
        entity_types: list[EntityType] | None = None,
        platforms: list[str] | None = None,
        limit: int = 20,
    ) -> tuple[list[SearchHit], list[DocumentHit]]:
        """Return ``(entity_hits, document_hits)``."""
        chunks = await self.pipeline.retrieve(query, top_k=max(limit * 2, 10))

        best_by_urn: dict[str, float] = {}
        documents: list[DocumentHit] = []
        for chunk in chunks:
            if chunk.entity_urn:
                best_by_urn[chunk.entity_urn] = max(
                    best_by_urn.get(chunk.entity_urn, 0.0), chunk.score
                )
            else:
                documents.append(chunk)

        entities = await self.repo.get_many_by_urns(list(best_by_urn))
        hits: list[SearchHit] = []
        for entity in entities:
            if entity_types and entity.entity_type not in entity_types:
                continue
            if platforms and entity.platform not in platforms:
                continue
            score = round(best_by_urn.get(entity.urn, 0.0), 4)
            hits.append(
                SearchHit(
                    urn=entity.urn,
                    name=entity.name,
                    qualified_name=entity.qualified_name,
                    entity_type=entity.entity_type,
                    platform=entity.platform,
                    description=entity.description,
                    score=score,
                    semantic_score=score,
                    matched_on=["semantic"],
                    highlights=[truncate(entity.description or "", 200)]
                    if entity.description
                    else [],
                )
            )

        hits.sort(key=lambda hit: hit.score, reverse=True)
        logger.debug(
            "semantic_search_completed",
            extra={"query": query, "entities": len(hits), "documents": len(documents)},
        )
        return hits[:limit], documents
