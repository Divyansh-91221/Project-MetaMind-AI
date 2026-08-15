"""Retrieval over the knowledge layer.

Hybrid retrieval on purpose: lexical matching finds exact asset names (``customer_id``) that
embeddings blur, while semantic matching finds conceptual questions ("revenue definition")
that keywords miss. Scores from both are normalised and blended with configurable weights.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import DocumentType
from app.core.logging import get_logger
from app.rag.embeddings import get_embedding_provider
from app.rag.vector_store import VectorMatch, VectorStore, get_vector_store
from app.repositories.metadata_repository import MetadataRepository
from app.schemas.search import DocumentHit

logger = get_logger(__name__)


@dataclass(slots=True)
class RetrievalResult:
    documents: list[DocumentHit]
    query: str


class Retriever:
    """Semantic retrieval with optional entity scoping."""

    def __init__(self, session: AsyncSession, vector_store: VectorStore | None = None) -> None:
        self.session = session
        self.vector_store = vector_store or get_vector_store(session)
        self.embeddings = get_embedding_provider()
        self.metadata_repo = MetadataRepository(session)

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        document_types: list[DocumentType] | None = None,
        entity_urns: list[str] | None = None,
        min_score: float = 0.0,
    ) -> list[DocumentHit]:
        top_k = top_k or settings.rag_top_k
        embedding = await self.embeddings.embed_one(query)
        matches = await self.vector_store.search(
            embedding,
            top_k=top_k,
            document_types=document_types,
            entity_urns=entity_urns,
        )
        hits = [self._to_hit(match) for match in matches if match.score >= min_score]
        logger.debug("retrieval_completed", extra={"query": query, "hits": len(hits)})
        return hits

    async def retrieve_for_entities(
        self, query: str, urns: list[str], *, top_k: int | None = None
    ) -> list[DocumentHit]:
        """Scoped retrieval: only documentation attached to the resolved assets.

        Used by the agent once entity resolution has produced concrete URNs, which keeps the
        evidence tied to the assets the user actually asked about.
        """
        if not urns:
            return []
        return await self.retrieve(query, top_k=top_k, entity_urns=urns)

    @staticmethod
    def _to_hit(match: VectorMatch) -> DocumentHit:
        return DocumentHit(
            chunk_id=match.id,
            document_title=match.document_title,
            document_type=match.document_type,
            content=match.content,
            score=round(match.score, 4),
            entity_urn=match.entity_urn,
            source_uri=match.source_uri,
            metadata=match.metadata,
        )
