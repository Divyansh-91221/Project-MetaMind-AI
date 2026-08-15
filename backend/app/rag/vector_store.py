"""Vector store abstraction.

Rule: the vector store is a **retrieval index**, never the source of truth. It holds
unstructured documentation only - structured metadata lives in PostgreSQL and lineage in the
graph. Two implementations ship today (pgvector and in-memory); adding a dedicated vector
database means implementing this protocol and registering it in :func:`get_vector_store`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import DocumentType
from app.core.logging import get_logger
from app.models.documents import Document, DocumentChunk
from app.rag.embeddings import cosine_similarity

logger = get_logger(__name__)


@dataclass(slots=True)
class VectorRecord:
    """A chunk ready to be indexed."""

    content: str
    embedding: list[float]
    document_id: uuid.UUID
    chunk_index: int = 0
    document_title: str = ""
    document_type: DocumentType = DocumentType.DATA_DOCUMENTATION
    entity_urn: str | None = None
    source_uri: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: uuid.UUID | None = None


@dataclass(slots=True)
class VectorMatch:
    """A retrieved chunk with its similarity score and provenance."""

    id: str
    content: str
    score: float
    document_title: str
    document_type: DocumentType
    entity_urn: str | None = None
    source_uri: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class VectorStore(Protocol):
    """Storage-agnostic semantic index."""

    async def upsert(self, records: list[VectorRecord]) -> int: ...

    async def search(
        self,
        embedding: list[float],
        *,
        top_k: int = 8,
        document_types: list[DocumentType] | None = None,
        entity_urns: list[str] | None = None,
    ) -> list[VectorMatch]: ...

    async def delete_document(self, document_id: uuid.UUID) -> int: ...

    async def clear(self) -> None: ...


class PgVectorStore:
    """pgvector-backed store using the ``document_chunks`` table.

    Keeping embeddings in PostgreSQL means one backup, one transaction boundary and one set
    of access controls for the first deployment.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(self, records: list[VectorRecord]) -> int:
        if not records:
            return 0
        for record in records:
            chunk = DocumentChunk(
                id=record.id or uuid.uuid4(),
                document_id=record.document_id,
                chunk_index=record.chunk_index,
                content=record.content,
                entity_urn=record.entity_urn,
                document_type=record.document_type,
                embedding=record.embedding,
                chunk_metadata={
                    **record.metadata,
                    "document_title": record.document_title,
                    "source_uri": record.source_uri,
                },
            )
            self.session.add(chunk)
        await self.session.flush()
        return len(records)

    async def search(
        self,
        embedding: list[float],
        *,
        top_k: int = 8,
        document_types: list[DocumentType] | None = None,
        entity_urns: list[str] | None = None,
    ) -> list[VectorMatch]:
        # ``<=>`` is pgvector's cosine distance operator; similarity = 1 - distance.
        stmt = (
            select(
                DocumentChunk,
                Document.title,
                Document.source_uri,
                (1 - DocumentChunk.embedding.cosine_distance(embedding)).label("score"),
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.embedding.is_not(None))
            .order_by(DocumentChunk.embedding.cosine_distance(embedding))
            .limit(top_k)
        )
        if document_types:
            stmt = stmt.where(DocumentChunk.document_type.in_(document_types))
        if entity_urns:
            stmt = stmt.where(DocumentChunk.entity_urn.in_(entity_urns))

        rows = (await self.session.execute(stmt)).all()
        return [
            VectorMatch(
                id=str(row[0].id),
                content=row[0].content,
                score=float(row[3] or 0.0),
                document_title=row[1],
                document_type=row[0].document_type,
                entity_urn=row[0].entity_urn,
                source_uri=row[2],
                metadata=row[0].chunk_metadata,
            )
            for row in rows
        ]

    async def delete_document(self, document_id: uuid.UUID) -> int:
        result = await self.session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        return int(result.rowcount or 0)

    async def clear(self) -> None:
        await self.session.execute(text("TRUNCATE TABLE document_chunks CASCADE"))


class InMemoryVectorStore:
    """Dictionary-backed store for tests and for running without pgvector."""

    def __init__(self) -> None:
        self._records: dict[str, VectorRecord] = {}

    async def upsert(self, records: list[VectorRecord]) -> int:
        for record in records:
            key = str(record.id or uuid.uuid4())
            record.id = uuid.UUID(key)
            self._records[key] = record
        return len(records)

    async def search(
        self,
        embedding: list[float],
        *,
        top_k: int = 8,
        document_types: list[DocumentType] | None = None,
        entity_urns: list[str] | None = None,
    ) -> list[VectorMatch]:
        matches: list[VectorMatch] = []
        for key, record in self._records.items():
            if document_types and record.document_type not in document_types:
                continue
            if entity_urns and record.entity_urn not in entity_urns:
                continue
            matches.append(
                VectorMatch(
                    id=key,
                    content=record.content,
                    score=cosine_similarity(embedding, record.embedding),
                    document_title=record.document_title,
                    document_type=record.document_type,
                    entity_urn=record.entity_urn,
                    source_uri=record.source_uri,
                    metadata=record.metadata,
                )
            )
        matches.sort(key=lambda match: match.score, reverse=True)
        return matches[:top_k]

    async def delete_document(self, document_id: uuid.UUID) -> int:
        keys = [k for k, v in self._records.items() if v.document_id == document_id]
        for key in keys:
            del self._records[key]
        return len(keys)

    async def clear(self) -> None:
        self._records.clear()


_memory_store = InMemoryVectorStore()


def get_vector_store(session: AsyncSession) -> VectorStore:
    """Return the configured vector store.

    The in-memory store is process-wide; the pgvector store is session-scoped because it takes
    part in the request transaction.
    """
    if settings.vector_store == "memory":
        return _memory_store
    return PgVectorStore(session)
