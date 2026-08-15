"""Business glossary endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentPrincipal, DbSession, Pagination
from app.core.security import Permission
from app.schemas.common import OperationResult, Page
from app.schemas.glossary import (
    BusinessTermCreate,
    BusinessTermDetail,
    BusinessTermRead,
    TermAssignmentRequest,
)
from app.services.glossary.glossary_service import GlossaryService

router = APIRouter(prefix="/glossary", tags=["glossary"])


@router.get("", response_model=Page[BusinessTermRead], summary="List business terms")
async def list_terms(
    session: DbSession,
    principal: CurrentPrincipal,
    pagination: Pagination,
    kpi_only: Annotated[bool, Query(description="Return only KPIs.")] = False,
) -> Page[BusinessTermRead]:
    principal.require(Permission.METADATA_READ)
    return await GlossaryService(session).list_terms(
        kpi_only=kpi_only, limit=pagination.limit, offset=pagination.offset
    )


@router.post(
    "",
    response_model=BusinessTermRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create or update a business term",
)
async def create_term(
    payload: BusinessTermCreate, session: DbSession, principal: CurrentPrincipal
) -> BusinessTermRead:
    principal.require(Permission.GOVERNANCE_WRITE)
    return await GlossaryService(session).create_term(payload)


@router.post("/assign", response_model=OperationResult, summary="Link a term to an asset")
async def assign_term(
    payload: TermAssignmentRequest, session: DbSession, principal: CurrentPrincipal
) -> OperationResult:
    principal.require(Permission.GOVERNANCE_WRITE)
    await GlossaryService(session).assign_term(payload)
    return OperationResult(message=f"'{payload.term_name}' linked to {payload.entity_urn}.", affected=1)


@router.get("/search", response_model=list[BusinessTermRead], summary="Search the glossary")
async def search_terms(
    session: DbSession,
    principal: CurrentPrincipal,
    q: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[BusinessTermRead]:
    principal.require(Permission.METADATA_READ)
    return await GlossaryService(session).search(q, limit=limit)


@router.get("/{term:path}", response_model=BusinessTermDetail, summary="Get a business term")
async def get_term(
    term: str, session: DbSession, principal: CurrentPrincipal
) -> BusinessTermDetail:
    principal.require(Permission.METADATA_READ)
    return await GlossaryService(session).get_term(term)
