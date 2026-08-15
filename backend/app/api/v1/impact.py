"""Impact analysis endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentPrincipal, DbSession
from app.core.security import Permission
from app.schemas.impact import DependencyReport, ImpactAnalysisResult
from app.services.impact.impact_service import ImpactService

router = APIRouter(prefix="/impact", tags=["impact"])


@router.get(
    "/{entity_urn:path}/dependencies",
    response_model=DependencyReport,
    summary="What this asset depends on",
)
async def dependencies(
    entity_urn: str,
    session: DbSession,
    principal: CurrentPrincipal,
    depth: Annotated[int, Query(ge=1, le=15)] = 5,
) -> DependencyReport:
    principal.require(Permission.LINEAGE_READ)
    return await ImpactService(session).dependencies(entity_urn, depth=depth)


@router.get(
    "/{entity_urn:path}",
    response_model=ImpactAnalysisResult,
    summary="What breaks if this asset changes",
)
async def impact(
    entity_urn: str,
    session: DbSession,
    principal: CurrentPrincipal,
    depth: Annotated[int, Query(ge=1, le=15)] = 8,
    min_confidence: Annotated[float, Query(ge=0.0, le=1.0)] = 0.0,
) -> ImpactAnalysisResult:
    principal.require(Permission.LINEAGE_READ)
    return await ImpactService(session).analyze(
        entity_urn, depth=depth, min_confidence=min_confidence
    )
