"""Hybrid search service - the entry point used by the API and the agent.

Blends lexical and semantic scores with configurable weights. Hybrid is the default because
metadata queries are a mix of exact identifiers ("customer_id") and conceptual questions
("which datasets describe revenue?"), and neither strategy handles both well alone.
"""

from __future__ import annotations

import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.constants import SearchMode
from app.core.logging import get_logger
from app.rag.rag_pipeline import RAGPipeline
from app.schemas.search import (
    DocumentHit,
    IndexRequest,
    RetrievalResponse,
    SearchHit,
    SearchRequest,
    SearchResponse,
)
from app.services.search.metadata_search import MetadataSearch
from app.services.search.semantic_search import SemanticSearch

logger = get_logger(__name__)


class SearchService:
    """Keyword, semantic and hybrid search plus index maintenance."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.pipeline = RAGPipeline(session)
        self.keyword = MetadataSearch(session)
        self.semantic = SemanticSearch(session, self.pipeline)

    async def search(self, request: SearchRequest) -> SearchResponse:
        started = time.perf_counter()

        if request.mode is SearchMode.KEYWORD:
            hits = await self.keyword.search(
                request.q,
                entity_types=request.entity_types or None,
                platforms=request.platforms or None,
                limit=request.limit,
            )
        elif request.mode is SearchMode.SEMANTIC:
            hits, _ = await self.semantic.search(
                request.q,
                entity_types=request.entity_types or None,
                platforms=request.platforms or None,
                limit=request.limit,
            )
        else:
            hits = await self._hybrid(request)

        hits = [hit for hit in hits if hit.score >= request.min_score][: request.limit]
        return SearchResponse(
            query=request.q,
            mode=request.mode,
            total=len(hits),
            hits=hits,
            took_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    async def _hybrid(self, request: SearchRequest) -> list[SearchHit]:
        keyword_hits = await self.keyword.search(
            request.q,
            entity_types=request.entity_types or None,
            platforms=request.platforms or None,
            limit=request.limit * 2,
        )
        semantic_hits, _ = await self.semantic.search(
            request.q,
            entity_types=request.entity_types or None,
            platforms=request.platforms or None,
            limit=request.limit * 2,
        )

        merged: dict[str, SearchHit] = {}
        for hit in keyword_hits:
            merged[hit.urn] = hit
        for hit in semantic_hits:
            existing = merged.get(hit.urn)
            if existing is None:
                merged[hit.urn] = hit
            else:
                existing.semantic_score = hit.semantic_score
                existing.matched_on = sorted({*existing.matched_on, *hit.matched_on})

        for hit in merged.values():
            hit.score = round(
                settings.hybrid_keyword_weight * hit.keyword_score
                + settings.hybrid_semantic_weight * hit.semantic_score,
                4,
            )

        return sorted(merged.values(), key=lambda hit: hit.score, reverse=True)

    async def retrieve(
        self, query: str, *, entity_urns: list[str] | None = None, top_k: int | None = None
    ) -> RetrievalResponse:
        """Hybrid retrieval for the agent: documents plus the assets they describe."""
        documents: list[DocumentHit] = await self.pipeline.retrieve(
            query, entity_urns=entity_urns, top_k=top_k
        )
        entities = await self._hybrid(
            SearchRequest(q=query, mode=SearchMode.HYBRID, limit=top_k or settings.rag_top_k)
        )
        return RetrievalResponse(query=query, documents=documents, entities=entities)

    async def reindex(self, request: IndexRequest) -> dict[str, int]:
        """Rebuild or refresh the semantic index."""
        report = await self.pipeline.index_catalog(entity_urns=request.entity_urns or None)
        totals = {
            "documents_indexed": report.documents_indexed,
            "chunks_indexed": report.chunks_indexed,
            "skipped_unchanged": report.skipped_unchanged,
        }
        if request.include_glossary:
            glossary = await self.pipeline.index_glossary()
            totals["documents_indexed"] += glossary.documents_indexed
            totals["chunks_indexed"] += glossary.chunks_indexed
            totals["skipped_unchanged"] += glossary.skipped_unchanged
        logger.info("search_index_refreshed", extra=totals)
        return totals
