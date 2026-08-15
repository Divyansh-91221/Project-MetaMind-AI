"""Lineage endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentPrincipal, DbSession
from app.core.constants import Direction, LineageLevel
from app.core.security import Permission
from app.schemas.common import OperationResult
from app.schemas.lineage import (
    LineageEdgeCreate,
    LineageEdgeRead,
    LineageGraph,
    LineagePath,
    LineageQuery,
    LineageVerificationRequest,
    SqlLineageRequest,
    SqlLineageResult,
)
from app.services.lineage.lineage_service import LineageService

router = APIRouter(prefix="/lineage", tags=["lineage"])


def _query(
    depth: int, level: LineageLevel | None, min_confidence: float, include_inferred: bool
) -> LineageQuery:
    return LineageQuery(
        depth=depth,
        level=level,
        min_confidence=min_confidence,
        include_inferred=include_inferred,
    )


@router.post("/parse-sql", response_model=SqlLineageResult, summary="Extract lineage from SQL")
async def parse_sql(
    payload: SqlLineageRequest, session: DbSession, principal: CurrentPrincipal
) -> SqlLineageResult:
    """Parse SQL with SQLGlot. Set ``persist=true`` to store the extracted lineage."""
    if payload.persist:
        principal.require(Permission.METADATA_WRITE)
    else:
        principal.require(Permission.LINEAGE_READ)
    return await LineageService(session).parse_sql(payload, principal=principal.subject)


@router.post("/edges", response_model=OperationResult, summary="Assert lineage manually")
async def create_edge(
    payload: LineageEdgeCreate, session: DbSession, principal: CurrentPrincipal
) -> OperationResult:
    principal.require(Permission.LINEAGE_VERIFY)
    created, updated = await LineageService(session).add_manual_edge(
        payload, principal=principal.subject
    )
    return OperationResult(
        message=f"{created} edge(s) created, {updated} updated.", affected=created + updated
    )


@router.get(
    "/review-queue",
    response_model=list[LineageEdgeRead],
    summary="Lineage edges awaiting human verification",
)
async def review_queue(
    session: DbSession,
    principal: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[LineageEdgeRead]:
    principal.require(Permission.LINEAGE_READ)
    return await LineageService(session).review_queue(limit=limit)


@router.post(
    "/edges/{edge_id}/verify",
    response_model=LineageEdgeRead,
    summary="Record a human verification decision",
)
async def verify_edge(
    edge_id: uuid.UUID,
    payload: LineageVerificationRequest,
    session: DbSession,
    principal: CurrentPrincipal,
) -> LineageEdgeRead:
    """Human validation of (usually AI-inferred) lineage. Always audited."""
    principal.require(Permission.LINEAGE_VERIFY)
    return await LineageService(session).verify_edge(
        edge_id, status=payload.status, principal=principal.subject, note=payload.note
    )


@router.post("/rebuild-graph", response_model=OperationResult, summary="Rebuild the graph")
async def rebuild_graph(session: DbSession, principal: CurrentPrincipal) -> OperationResult:
    """Re-project PostgreSQL lineage into the graph store. Safe to run at any time."""
    principal.require(Permission.METADATA_WRITE)
    stats = await LineageService(session).rebuild_graph(principal=principal.subject)
    return OperationResult(message="Graph projection rebuilt.", affected=stats["edges"])


@router.get("/paths", response_model=list[LineagePath], summary="Find lineage paths")
async def lineage_paths(
    session: DbSession,
    principal: CurrentPrincipal,
    source_urn: Annotated[str, Query(description="Upstream asset URN.")],
    target_urn: Annotated[str, Query(description="Downstream asset URN.")],
    max_depth: Annotated[int, Query(ge=1, le=15)] = 10,
) -> list[LineagePath]:
    principal.require(Permission.LINEAGE_READ)
    return await LineageService(session).get_paths(source_urn, target_urn, max_depth=max_depth)


@router.get(
    "/{entity_urn:path}/upstream",
    response_model=LineageGraph,
    summary="Upstream lineage",
)
async def upstream(
    entity_urn: str,
    session: DbSession,
    principal: CurrentPrincipal,
    depth: Annotated[int, Query(ge=1, le=15)] = 3,
    level: LineageLevel | None = None,
    min_confidence: Annotated[float, Query(ge=0.0, le=1.0)] = 0.0,
    include_inferred: bool = True,
) -> LineageGraph:
    principal.require(Permission.LINEAGE_READ)
    return await LineageService(session).get_lineage(
        entity_urn,
        direction=Direction.UPSTREAM,
        query=_query(depth, level, min_confidence, include_inferred),
    )


@router.get(
    "/{entity_urn:path}/downstream",
    response_model=LineageGraph,
    summary="Downstream lineage",
)
async def downstream(
    entity_urn: str,
    session: DbSession,
    principal: CurrentPrincipal,
    depth: Annotated[int, Query(ge=1, le=15)] = 3,
    level: LineageLevel | None = None,
    min_confidence: Annotated[float, Query(ge=0.0, le=1.0)] = 0.0,
    include_inferred: bool = True,
) -> LineageGraph:
    principal.require(Permission.LINEAGE_READ)
    return await LineageService(session).get_lineage(
        entity_urn,
        direction=Direction.DOWNSTREAM,
        query=_query(depth, level, min_confidence, include_inferred),
    )


@router.get(
    "/{entity_urn:path}/edges",
    response_model=list[LineageEdgeRead],
    summary="Direct lineage edges from PostgreSQL",
)
async def direct_edges(
    entity_urn: str, session: DbSession, principal: CurrentPrincipal
) -> list[LineageEdgeRead]:
    """One-hop edges read from the source of truth rather than the graph projection."""
    principal.require(Permission.LINEAGE_READ)
    return await LineageService(session).get_direct_edges(entity_urn)


@router.get(
    "/{entity_urn:path}",
    response_model=LineageGraph,
    summary="Lineage in both directions",
)
async def lineage(
    entity_urn: str,
    session: DbSession,
    principal: CurrentPrincipal,
    depth: Annotated[int, Query(ge=1, le=15)] = 3,
    level: LineageLevel | None = None,
    min_confidence: Annotated[float, Query(ge=0.0, le=1.0)] = 0.0,
    include_inferred: bool = True,
) -> LineageGraph:
    principal.require(Permission.LINEAGE_READ)
    return await LineageService(session).get_lineage(
        entity_urn,
        direction=Direction.BOTH,
        query=_query(depth, level, min_confidence, include_inferred),
    )
