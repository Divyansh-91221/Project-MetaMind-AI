"""RAG pipeline: indexing and grounded retrieval.

Indexing turns catalog descriptions, glossary terms and documentation into embedded chunks.
Retrieval returns chunks *with provenance* so the agent can cite them. The pipeline never
answers questions itself - it supplies evidence to the agent layer.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import DocumentType
from app.core.logging import get_logger
from app.models.documents import Document
from app.models.glossary import BusinessTerm
from app.rag.chunking import TextChunker
from app.rag.document_loader import DocumentLoader, LoadedDocument
from app.rag.embeddings import get_embedding_provider
from app.rag.retriever import Retriever
from app.rag.vector_store import VectorRecord, VectorStore, get_vector_store
from app.repositories.glossary_repository import GlossaryRepository
from app.repositories.governance_repository import GovernanceRepository
from app.repositories.metadata_repository import MetadataRepository
from app.schemas.search import DocumentHit

logger = get_logger(__name__)


@dataclass(slots=True)
class IndexingReport:
    documents_indexed: int = 0
    chunks_indexed: int = 0
    skipped_unchanged: int = 0


class RAGPipeline:
    """Owns the document -> chunk -> embedding -> index flow and grounded retrieval."""

    def __init__(self, session: AsyncSession, vector_store: VectorStore | None = None) -> None:
        self.session = session
        self.vector_store = vector_store or get_vector_store(session)
        self.embeddings = get_embedding_provider()
        self.chunker = TextChunker()
        self.loader = DocumentLoader()
        self.retriever = Retriever(session, self.vector_store)
        self.metadata_repo = MetadataRepository(session)
        self.glossary_repo = GlossaryRepository(session)
        self.governance_repo = GovernanceRepository(session)

    # ------------------------------------------------------------------ #
    # Indexing
    # ------------------------------------------------------------------ #
    async def index_documents(self, documents: list[LoadedDocument]) -> IndexingReport:
        report = IndexingReport()
        for loaded in documents:
            existing = await self._existing_document(loaded)
            if existing is not None and existing.content_hash == loaded.content_hash:
                report.skipped_unchanged += 1
                continue

            if existing is not None:
                await self.vector_store.delete_document(existing.id)
                document = existing
                document.title = loaded.title
                document.content_hash = loaded.content_hash
                document.doc_metadata = loaded.metadata
            else:
                document = Document(
                    id=uuid.uuid4(),
                    title=loaded.title,
                    document_type=loaded.document_type,
                    source_uri=loaded.source_uri,
                    entity_urn=loaded.entity_urn,
                    content_hash=loaded.content_hash,
                    doc_metadata=loaded.metadata,
                )
                self.session.add(document)
            await self.session.flush()

            chunks = self.chunker.split(loaded.content, metadata=loaded.metadata)
            if not chunks:
                continue
            vectors = await self.embeddings.embed([chunk.content for chunk in chunks])
            await self.vector_store.upsert(
                [
                    VectorRecord(
                        content=chunk.content,
                        embedding=vector,
                        document_id=document.id,
                        chunk_index=chunk.index,
                        document_title=loaded.title,
                        document_type=loaded.document_type,
                        entity_urn=loaded.entity_urn,
                        source_uri=loaded.source_uri,
                        metadata=chunk.metadata,
                    )
                    for chunk, vector in zip(chunks, vectors, strict=True)
                ]
            )
            report.documents_indexed += 1
            report.chunks_indexed += len(chunks)

        logger.info(
            "rag_indexing_completed",
            extra={
                "documents": report.documents_indexed,
                "chunks": report.chunks_indexed,
                "skipped": report.skipped_unchanged,
            },
        )
        return report

    async def index_catalog(self, *, entity_urns: list[str] | None = None) -> IndexingReport:
        """Index catalog descriptions so assets are semantically discoverable."""
        if entity_urns:
            entities = await self.metadata_repo.get_many_by_urns(entity_urns)
        else:
            entities, _ = await self.metadata_repo.list_entities(limit=100_000)

        documents: list[LoadedDocument] = []
        for entity in entities:
            if not entity.description and not entity.tags:
                continue
            context: dict[str, list[str]] = {}
            owners = await self.governance_repo.owners_for_entity(entity.id)
            if owners:
                context["owners"] = [assignment.owner.name for assignment in owners]
            classifications = await self.governance_repo.classifications_for_entity(entity.id)
            if classifications:
                context["classifications"] = [
                    assignment.classification.name for assignment in classifications
                ]
            columns = await self.metadata_repo.get_children(entity.id)
            if columns:
                context["columns"] = [column.name for column in columns[:50]]
            documents.append(self.loader.from_entity(entity, context=context))

        return await self.index_documents(documents)

    async def index_glossary(self) -> IndexingReport:
        terms = (await self.session.execute(select(BusinessTerm))).scalars().all()
        return await self.index_documents([self.loader.from_business_term(t) for t in terms])

    async def index_directory(
        self, directory: str, *, document_type: DocumentType | None = None
    ) -> IndexingReport:
        return await self.index_documents(
            self.loader.from_directory(directory, document_type=document_type)
        )

    # ------------------------------------------------------------------ #
    # Retrieval
    # ------------------------------------------------------------------ #
    async def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        entity_urns: list[str] | None = None,
        document_types: list[DocumentType] | None = None,
    ) -> list[DocumentHit]:
        """Grounded retrieval: entity-scoped first, then a global fallback."""
        top_k = top_k or settings.rag_top_k
        hits: list[DocumentHit] = []
        if entity_urns:
            hits = await self.retriever.retrieve_for_entities(query, entity_urns, top_k=top_k)
        if len(hits) < top_k:
            seen = {hit.chunk_id for hit in hits}
            extra = await self.retriever.retrieve(
                query, top_k=top_k - len(hits), document_types=document_types
            )
            hits.extend(hit for hit in extra if hit.chunk_id not in seen)
        return hits[:top_k]

    async def _existing_document(self, loaded: LoadedDocument) -> Document | None:
        stmt = select(Document).where(Document.source_uri == loaded.source_uri)
        return (await self.session.execute(stmt)).scalars().first()
