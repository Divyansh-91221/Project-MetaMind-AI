"""Governance endpoints: ownership, classification and policy."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentPrincipal, DbSession
from app.core.constants import SensitivityTag
from app.core.security import Permission
from app.schemas.governance import (
    ClassificationReviewRequest,
    GovernanceProfile,
    OwnerCreate,
    OwnerRead,
    OwnershipAssignment,
    OwnershipRead,
    SensitiveAssetRead,
    SensitiveAssetsQuery,
)
from app.services.governance.governance_service import GovernanceService

router = APIRouter(prefix="/governance", tags=["governance"])


@router.get("/owners", response_model=list[OwnerRead], summary="List owners")
async def list_owners(session: DbSession, principal: CurrentPrincipal) -> list[OwnerRead]:
    principal.require(Permission.METADATA_READ)
    return await GovernanceService(session).list_owners()


@router.post(
    "/owners",
    response_model=OwnerRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create or update an owner",
)
async def create_owner(
    payload: OwnerCreate, session: DbSession, principal: CurrentPrincipal
) -> OwnerRead:
    principal.require(Permission.GOVERNANCE_WRITE)
    return await GovernanceService(session).create_owner(payload)


@router.post("/ownership", response_model=OwnershipRead, summary="Assign ownership")
async def assign_owner(
    payload: OwnershipAssignment, session: DbSession, principal: CurrentPrincipal
) -> OwnershipRead:
    principal.require(Permission.GOVERNANCE_WRITE)
    return await GovernanceService(session).assign_owner(payload, principal=principal.subject)


@router.get("/sensitive", response_model=list[SensitiveAssetRead], summary="Assets carrying a sensitivity tag")
async def sensitive_assets(
    session: DbSession,
    principal: CurrentPrincipal,
    sensitivity: SensitivityTag = SensitivityTag.PII,
    platform: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[dict[str, Any]]:
    """Answers "which datasets contain PII?"."""
    principal.require(Permission.METADATA_READ)
    return await GovernanceService(session).sensitive_assets(
        SensitiveAssetsQuery(sensitivity=sensitivity, platform=platform, limit=limit)
    )


@router.get("/classification-review-history", summary="Classification review history")
async def classification_review_history(
    session: DbSession,
    principal: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[dict[str, Any]]:
    principal.require(Permission.METADATA_READ)
    return await GovernanceService(session).classification_review_history(limit=limit)


@router.get("/enrichment-review-history", summary="Enrichment approval history")
async def enrichment_review_history(
    session: DbSession,
    principal: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[dict[str, Any]]:
    principal.require(Permission.METADATA_READ)
    return await GovernanceService(session).enrichment_review_history(limit=limit)


@router.post(
    "/classifications/{assignment_id}/review",
    response_model=SensitiveAssetRead,
    summary="Confirm or reject a classification assignment",
)
async def review_classification(
    assignment_id: str,
    payload: ClassificationReviewRequest,
    session: DbSession,
    principal: CurrentPrincipal,
) -> SensitiveAssetRead:
    principal.require(Permission.GOVERNANCE_WRITE)
    from uuid import UUID

    return await GovernanceService(session).review_classification(
        UUID(assignment_id), payload, principal=principal.subject
    )


@router.get("/unowned", summary="Assets without an accountable owner")
async def unowned_assets(
    session: DbSession,
    principal: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[dict[str, str]]:
    principal.require(Permission.METADATA_READ)
    return await GovernanceService(session).unowned_assets(limit=limit)


@router.get(
    "/{entity_urn:path}",
    response_model=GovernanceProfile,
    summary="Governance profile of an asset",
)
async def governance_profile(
    entity_urn: str, session: DbSession, principal: CurrentPrincipal
) -> GovernanceProfile:
    principal.require(Permission.METADATA_READ)
    return await GovernanceService(session).get_profile(entity_urn)
