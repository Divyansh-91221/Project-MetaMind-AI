"""Search and retrieval API contracts."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.core.constants import DocumentType, EntityType, SearchMode
from app.schemas.common import APIModel


class SearchRequest(APIModel):
    q: str = Field(min_length=1, max_length=512, description="Natural language or keyword query.")
    mode: SearchMode = SearchMode.HYBRID
    entity_types: list[EntityType] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=100)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


class SearchHit(APIModel):
    """A ranked catalog result with explainable scoring."""

    urn: str
    name: str
    qualified_name: str
    entity_type: EntityType
    platform: str
    description: str | None = None
    score: float = Field(ge=0.0)
    keyword_score: float = 0.0
    semantic_score: float = 0.0
    matched_on: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)


class SearchResponse(APIModel):
    query: str
    mode: SearchMode
    total: int = 0
    hits: list[SearchHit] = Field(default_factory=list)
    took_ms: float = 0.0


class DocumentHit(APIModel):
    """A retrieved RAG chunk with provenance for citation."""

    chunk_id: str
    document_title: str
    document_type: DocumentType
    content: str
    score: float = 0.0
    entity_urn: str | None = None
    source_uri: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalResponse(APIModel):
    query: str
    documents: list[DocumentHit] = Field(default_factory=list)
    entities: list[SearchHit] = Field(default_factory=list)


class IndexRequest(APIModel):
    """Re-index catalog descriptions and documents into the vector store."""

    entity_urns: list[str] = Field(default_factory=list)
    include_glossary: bool = True
    include_documents: bool = True
    rebuild: bool = False
