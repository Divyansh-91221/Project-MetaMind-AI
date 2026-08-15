"""Metadata catalog endpoints. Routes stay thin - all logic lives in MetadataService."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, status

from app.api.deps import CurrentPrincipal, DbSession, Pagination
from app.core.constants import EntityType
from app.core.security import Permission
from app.ingestion.pipeline import IngestionPipeline
from app.schemas.common import Page
from app.schemas.metadata import (
    IngestionRequest,
    IngestionResult,
    MetadataEntityDetail,
    MetadataEntityRead,
    MetadataEntityUpdate,
    MetadataFilter,
)
from app.services.metadata.metadata_service import MetadataService

router = APIRouter(prefix="/metadata", tags=["metadata"])


@router.get("", response_model=Page[MetadataEntityRead], summary="List catalog entities")
async def list_metadata(
    session: DbSession,
    principal: CurrentPrincipal,
    pagination: Pagination,
    entity_type: Annotated[EntityType | None, Query(description="Filter by entity type.")] = None,
    platform: Annotated[str | None, Query(description="Filter by source platform.")] = None,
    parent_urn: Annotated[str | None, Query(description="Only children of this asset.")] = None,
    search: Annotated[str | None, Query(description="Substring match on name/description.")] = None,
    tag: Annotated[str | None, Query(description="Filter by tag.")] = None,
) -> Page[MetadataEntityRead]:
    principal.require(Permission.METADATA_READ)
    filters = MetadataFilter(
        entity_type=entity_type,
        platform=platform,
        parent_urn=parent_urn,
        search=search,
        tag=tag,
    )
    return await MetadataService(session).list_entities(
        filters, limit=pagination.limit, offset=pagination.offset
    )


@router.get("/summary", summary="Catalog counters for the dashboard")
async def catalog_summary(session: DbSession, principal: CurrentPrincipal) -> dict:
    principal.require(Permission.METADATA_READ)
    return await MetadataService(session).catalog_summary()


@router.post(
    "/ingest",
    response_model=IngestionResult,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run a metadata ingestion job",
)
async def ingest_metadata(
    payload: IngestionRequest,
    session: DbSession,
    principal: CurrentPrincipal,
    background_tasks: BackgroundTasks,
) -> IngestionResult:
    """Run ingestion synchronously and schedule a graph refresh afterwards.

    TODO: move to a task queue and return a job handle once ingestion volumes grow.
    """
    principal.require(Permission.METADATA_WRITE)
    result = await IngestionPipeline(session).run(payload, principal=principal.subject)

    from app.ingestion.jobs import rebuild_graph_job

    background_tasks.add_task(rebuild_graph_job, principal=principal.subject)
    return result


@router.get(
    "/{urn:path}/columns",
    response_model=list[MetadataEntityRead],
    summary="List the columns of a table or dataset",
)
async def list_columns(
    urn: str, session: DbSession, principal: CurrentPrincipal
) -> list[MetadataEntityRead]:
    principal.require(Permission.METADATA_READ)
    return await MetadataService(session).get_columns(urn)


@router.patch(
    "/{urn:path}",
    response_model=MetadataEntityRead,
    summary="Update curated metadata fields",
)
async def update_metadata(
    urn: str,
    payload: MetadataEntityUpdate,
    session: DbSession,
    principal: CurrentPrincipal,
) -> MetadataEntityRead:
    principal.require(Permission.METADATA_WRITE)
    return await MetadataService(session).update_entity(
        urn, payload, principal=principal.subject
    )


@router.get(
    "/{urn:path}",
    response_model=MetadataEntityDetail,
    summary="Get a single asset with full context",
)
async def get_metadata(
    urn: str, session: DbSession, principal: CurrentPrincipal
) -> MetadataEntityDetail:
    principal.require(Permission.METADATA_READ)
    return await MetadataService(session).get_entity_detail(urn)
