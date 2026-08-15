"""Data quality and freshness endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentPrincipal, DbSession
from app.core.security import Permission
from app.schemas.quality import (
    QualityMetricCreate,
    QualityMetricRead,
    QualityProfile,
    StalenessExplanation,
)
from app.services.quality.quality_service import QualityService

router = APIRouter(prefix="/quality", tags=["quality"])


@router.post(
    "/metrics",
    response_model=QualityMetricRead,
    status_code=status.HTTP_201_CREATED,
    summary="Record a quality measurement",
)
async def record_metric(
    payload: QualityMetricCreate, session: DbSession, principal: CurrentPrincipal
) -> QualityMetricRead:
    principal.require(Permission.METADATA_WRITE)
    return await QualityService(session).record_metric(payload)


@router.get("/stale", summary="Assets outside their freshness SLA")
async def stale_assets(
    session: DbSession,
    principal: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[dict[str, Any]]:
    principal.require(Permission.METADATA_READ)
    return await QualityService(session).stale_assets(limit=limit)


@router.get(
    "/{entity_urn:path}/staleness",
    response_model=StalenessExplanation,
    summary="Explain why an asset is stale",
)
async def explain_staleness(
    entity_urn: str, session: DbSession, principal: CurrentPrincipal
) -> StalenessExplanation:
    """Traces the root cause through upstream lineage and pipeline run status."""
    principal.require(Permission.METADATA_READ)
    return await QualityService(session).explain_staleness(entity_urn)


@router.get(
    "/{entity_urn:path}",
    response_model=QualityProfile,
    summary="Quality profile of an asset",
)
async def quality_profile(
    entity_urn: str, session: DbSession, principal: CurrentPrincipal
) -> QualityProfile:
    principal.require(Permission.METADATA_READ)
    return await QualityService(session).get_profile(entity_urn)
