"""Connector registration and discovery endpoints."""

from __future__ import annotations

import time

from fastapi import APIRouter, status

from app.api.deps import CurrentPrincipal, DbSession
from app.connectors.registry import create_connector, list_connectors
from app.core.constants import AuditAction, PlatformType
from app.core.security import Permission
from app.ingestion.run_history import group_ingestion_events
from app.repositories.audit_repository import AuditRepository
from app.repositories.metadata_repository import MetadataRepository
from app.schemas.connectors import (
    ConnectionTestResult,
    ConnectorDescriptor,
    DataSourceCreate,
    DataSourceRead,
    DemoResetResult,
    IngestionRunRead,
)
from app.schemas.metadata import IngestionRequest

router = APIRouter(prefix="/connectors", tags=["connectors"])


@router.get("", response_model=list[ConnectorDescriptor], summary="List available connectors")
async def available_connectors(principal: CurrentPrincipal) -> list[ConnectorDescriptor]:
    """Everything registered in the connector registry, implemented or not."""
    principal.require(Permission.METADATA_READ)
    return [
        ConnectorDescriptor(
            name=connector_cls.name,
            platform=connector_cls.platform,
            description=connector_cls.description,
            supports_lineage=connector_cls.capabilities.supports_lineage,
            supports_column_lineage=connector_cls.capabilities.supports_column_lineage,
            supports_quality=connector_cls.capabilities.supports_quality,
            implemented=connector_cls.capabilities.implemented,
            required_config=list(connector_cls.required_config),
        )
        for connector_cls in list_connectors()
    ]


@router.get("/sources", response_model=list[DataSourceRead], summary="List registered data sources")
async def list_sources(session: DbSession, principal: CurrentPrincipal) -> list[DataSourceRead]:
    principal.require(Permission.METADATA_READ)
    sources = await MetadataRepository(session).list_data_sources()
    return [DataSourceRead.model_validate(source) for source in sources]


@router.get(
    "/runs",
    response_model=list[IngestionRunRead],
    summary="Recent ingestion runs, assembled from the audit trail",
)
async def ingestion_runs(
    session: DbSession,
    principal: CurrentPrincipal,
    limit: int = 20,
) -> list[IngestionRunRead]:
    principal.require(Permission.METADATA_READ)
    events = await AuditRepository(session).list_events(
        actions=[
            AuditAction.INGESTION_STARTED,
            AuditAction.INGESTION_COMPLETED,
            AuditAction.INGESTION_FAILED,
        ],
        limit=max(limit * 3, 60),
    )
    runs = group_ingestion_events(events, limit=limit)
    return [IngestionRunRead.model_validate(run) for run in runs]


@router.post(
    "/demo/reset",
    response_model=DemoResetResult,
    summary="Reset and reseed the demo enterprise landscape",
)
async def reset_demo_data(principal: CurrentPrincipal) -> DemoResetResult:
    """Reingests the demo connector, rebuilds the graph and refreshes the search index.

    Reuses the same job functions the scheduler and background tasks call - there is no
    separate reset code path to keep in sync.
    """
    principal.require(Permission.CONNECTOR_MANAGE)
    from app.ingestion.jobs import rebuild_graph_job, reindex_job, run_ingestion_job

    result = await run_ingestion_job(
        IngestionRequest(
            connector="demo",
            data_source_name="demo-enterprise-landscape",
            full_refresh=True,
            extract_lineage=True,
        ),
        principal=principal.subject,
    )
    graph_job = await rebuild_graph_job(principal=principal.subject)
    index_job = await reindex_job(principal=principal.subject)
    return DemoResetResult(
        success=True,
        entities_created=result.entities_created,
        entities_updated=result.entities_updated,
        lineage_edges_created=result.lineage_edges_created,
        lineage_edges_updated=result.lineage_edges_updated,
        graph=graph_job.detail,
        index=index_job.detail,
    )


@router.post(
    "",
    response_model=DataSourceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a data source",
)
async def register_source(
    payload: DataSourceCreate, session: DbSession, principal: CurrentPrincipal
) -> DataSourceRead:
    """Register a connector instance.

    Credentials are never stored here - ``secret_ref`` points at the secret manager entry.
    """
    principal.require(Permission.CONNECTOR_MANAGE)
    connector = create_connector(payload.connector_type, payload.config)

    source = await MetadataRepository(session).upsert_data_source(
        payload.name,
        connector_type=connector.name,
        platform=connector.platform if connector.platform else PlatformType.UNKNOWN,
        description=payload.description or connector.description,
        config={k: v for k, v in payload.config.items() if "password" not in k.lower()},
        secret_ref=payload.secret_ref,
        enabled=payload.enabled,
    )
    await AuditRepository(session).record(
        AuditAction.CONNECTOR_REGISTERED,
        principal=principal.subject,
        resource_type="data_source",
        summary=f"Registered data source '{payload.name}' ({connector.name}).",
        payload={"connector": connector.name},
    )
    return DataSourceRead.model_validate(source)


@router.post(
    "/{connector_name}/test",
    response_model=ConnectionTestResult,
    summary="Test connectivity for a connector",
)
async def test_connector(
    connector_name: str, payload: dict[str, object], principal: CurrentPrincipal
) -> ConnectionTestResult:
    principal.require(Permission.CONNECTOR_MANAGE)
    connector = create_connector(connector_name, dict(payload))
    started = time.perf_counter()
    try:
        success, message = await connector.test_connection()
    finally:
        await connector.close()
    return ConnectionTestResult(
        success=success,
        message=message,
        latency_ms=round((time.perf_counter() - started) * 1000, 2),
    )
