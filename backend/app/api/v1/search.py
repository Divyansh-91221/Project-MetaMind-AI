"""Search and retrieval endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentPrincipal, DbSession
from app.core.constants import EntityType, SearchMode
from app.core.security import Permission
from app.schemas.search import (
    IndexRequest,
    RetrievalResponse,
    SearchRequest,
    SearchResponse,
)
from app.services.search.hybrid_search import SearchService

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse, summary="Search the catalog")
async def search(
    session: DbSession,
    principal: CurrentPrincipal,
    q: Annotated[str, Query(min_length=1, description="Natural language or keyword query.")],
    mode: SearchMode = SearchMode.HYBRID,
    entity_type: Annotated[list[EntityType] | None, Query()] = None,
    platform: Annotated[list[str] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SearchResponse:
    principal.require(Permission.METADATA_READ)
    return await SearchService(session).search(
        SearchRequest(
            q=q,
            mode=mode,
            entity_types=entity_type or [],
            platforms=platform or [],
            limit=limit,
        )
    )


@router.get(
    "/retrieve",
    response_model=RetrievalResponse,
    summary="Hybrid retrieval of documents and assets",
)
async def retrieve(
    session: DbSession,
    principal: CurrentPrincipal,
    q: Annotated[str, Query(min_length=1)],
    entity_urn: Annotated[list[str] | None, Query(description="Scope to these assets.")] = None,
    top_k: Annotated[int, Query(ge=1, le=50)] = 8,
) -> RetrievalResponse:
    """The RAG retrieval endpoint the Copilot uses internally - exposed for debugging."""
    principal.require(Permission.METADATA_READ)
    return await SearchService(session).retrieve(q, entity_urns=entity_urn, top_k=top_k)


@router.post("/reindex", summary="Rebuild the semantic index")
async def reindex(
    payload: IndexRequest, session: DbSession, principal: CurrentPrincipal
) -> dict[str, int]:
    principal.require(Permission.METADATA_WRITE)
    return await SearchService(session).reindex(payload)
