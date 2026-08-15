"""RAG document and chunk models.

Unstructured knowledge (descriptions, glossary text, policies, architecture docs, contracts)
is chunked and embedded here. Structured metadata and lineage are NOT stored here - the
vector store is a retrieval index, never a source of truth.
"""

from __future__ import annotations

import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Enum as SAEnum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.core.constants import DocumentType
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A source document that was loaded into the knowledge layer."""

    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_type", "document_type"),)

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    document_type: Mapped[DocumentType] = mapped_column(
        SAEnum(DocumentType, name="document_type"),
        nullable=False,
        default=DocumentType.DATA_DOCUMENTATION,
    )
    source_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Optional link back to the catalog object this document describes.
    entity_urn: Mapped[str | None] = mapped_column(String(1024), nullable=True, index=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    doc_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An embedded chunk used for semantic retrieval.

    The vector column dimension must match ``EMBEDDING_DIMENSION``. Changing providers with a
    different dimension requires a migration plus a re-index.
    """

    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("ix_document_chunks_document", "document_id"),
        Index("ix_document_chunks_entity_urn", "entity_urn"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    entity_urn: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    document_type: Mapped[DocumentType] = mapped_column(
        SAEnum(DocumentType, name="document_type", create_type=False), nullable=False
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.embedding_dimension), nullable=True
    )
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    document: Mapped[Document] = relationship(back_populates="chunks")
