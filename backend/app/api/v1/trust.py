"""Trust Center endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentPrincipal, DbSession
from app.core.security import Permission
from app.schemas.trust import AssetTrustSummary
from app.services.trust.trust_service import TrustService

router = APIRouter(prefix="/trust", tags=["trust"])


@router.get(
    "/{entity_urn:path}",
    response_model=AssetTrustSummary,
    summary="Aggregated trust summary for an asset",
)
async def asset_trust(
    entity_urn: str,
    session: DbSession,
    principal: CurrentPrincipal,
) -> AssetTrustSummary:
    principal.require(Permission.METADATA_READ)
    return await TrustService(session).get_asset_trust(entity_urn)
