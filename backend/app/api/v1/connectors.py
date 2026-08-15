"""Connector registration and discovery endpoints."""

from __future__ import annotations

import time

from fastapi import APIRouter, status

from app.api.deps import CurrentPrincipal, DbSession
from app.connectors.registry import create_connector, list_connectors
from app.core.constants import AuditAction, PlatformType
from app.core.security import Permission
from app.repositories.audit_repository import AuditRepository
from app.repositories.metadata_repository import MetadataRepository
from app.schemas.connectors import (
    ConnectionTestResult,
    ConnectorDescriptor,
    DataSourceCreate,
    DataSourceRead,
)

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


@router.get(
    "/sources", response_model=list[DataSourceRead], summary="List registered data sources"
)
async def list_sources(session: DbSession, principal: CurrentPrincipal) -> list[DataSourceRead]:
    principal.require(Permission.METADATA_READ)
    sources = await MetadataRepository(session).list_data_sources()
    return [DataSourceRead.model_validate(source) for source in sources]


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
